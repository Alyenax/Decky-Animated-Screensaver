"""Bounded, on-demand Unix client. No serial driver and no automatic write retry."""
from __future__ import annotations
import base64
import errno
import hashlib
import os
from pathlib import Path
import socket
import stat
import struct
import threading
import time
from uuid import uuid4
from .protocol import (PROTOCOL, VERSION, MESSAGE_BYTES, BrokerError, decode, encode,
                       identifier, integer, digest, validate_hello, validate_status, validate_lease)


class BrokerClient:
    def __init__(self, runtime_dir='/run/decky/jsaux-broker/v1', *, expected_uid=None,
                 monotonic=time.monotonic, socket_factory=socket.socket):
        self.runtime=Path(runtime_dir); self.uid=os.geteuid() if expected_uid is None else expected_uid
        self.clock=monotonic; self.socket_factory=socket_factory; self.instance=uuid4().hex
        self.lock=threading.RLock(); self.sock=None; self.boot=None; self.hello=None
        self.wire_version=VERSION;self.cached=None; self.retry_at=0.; self.failures=0; self._buffer=b'';self.last_io=0.
        self._diagnostic = {'state': 'not-checked'}
        self._diagnostic_revision = 0
        self._stage = 'filesystem'
        self._component = 'runtime'

    def diagnostic_snapshot(self):
        """Local, bounded metadata only; never credentials, paths or wire data."""
        # Writers replace the complete dictionary. Do not take the RPC lock:
        # opening a diagnostic must not wait for a content upload or timeout.
        return dict(self._diagnostic)

    def _component_label(self, path):
        labels = {
            self.runtime: 'runtime',
            self.runtime / 'credential.json': 'credential',
            self.runtime / 'control.sock': 'control-socket',
            self.runtime.parent: 'connection-root',
            self.runtime.parent.parent: 'decky-runtime',
            Path('/run'): 'system-runtime',
        }
        return labels.get(path, 'runtime-ancestor')

    def _checkpoint(self, stage, component):
        self._stage = stage
        self._component = component

    @staticmethod
    def _file_kind(mode):
        if stat.S_ISDIR(mode):
            return 'directory'
        if stat.S_ISREG(mode):
            return 'regular-file'
        if stat.S_ISSOCK(mode):
            return 'socket'
        if stat.S_ISLNK(mode):
            return 'symlink'
        return 'other'

    def _remember_failure(self, reason, code, *, info=None, expected_mode=None,
                          expected_kind=None, observed_uid=None, error_number=None):
        state = ('refused' if code == 'AUTH_DENIED' else
                 'request-refused' if reason == 'remote-rejected' else 'unavailable')
        value = dict(state=state,
                     stage=self._stage, component=self._component,
                     reason=reason, code=code)
        if type(self.uid) is int and 0 <= self.uid <= 0xffffffff:
            value['expected_uid'] = self.uid
        if info is not None:
            value.update(observed_uid=info.st_uid,
                         observed_mode=format(stat.S_IMODE(info.st_mode), '04o'),
                         observed_kind=self._file_kind(info.st_mode))
        elif observed_uid is not None:
            value['observed_uid'] = observed_uid
        if expected_mode is not None:
            value['expected_mode'] = format(expected_mode, '04o')
        if expected_kind is not None:
            value['expected_kind'] = expected_kind
        if error_number in {errno.EACCES, errno.EPERM, errno.ENOENT,
                            errno.ECONNREFUSED, errno.ETIMEDOUT}:
            value['errno'] = error_number
        self._diagnostic = value
        self._diagnostic_revision += 1

    def _deny(self, reason, **metadata):
        self._remember_failure(reason, 'AUTH_DENIED', **metadata)
        raise BrokerError('AUTH_DENIED')

    def _io_failure(self, error):
        number = getattr(error, 'errno', None)
        denied = number in {errno.EACCES, errno.EPERM}
        reason = ('system-permission-denied' if denied else
                  'missing' if number == errno.ENOENT else
                  'connection-refused' if number == errno.ECONNREFUSED else
                  'timeout' if isinstance(error, TimeoutError) else 'io-failed')
        code = 'AUTH_DENIED' if denied else 'BROKER_UNAVAILABLE'
        self._remember_failure(reason, code, error_number=number)
        return code

    def _private(self,path,kind,mode):
        expected_kind = ('directory' if kind is stat.S_ISDIR else
                         'socket' if kind is stat.S_ISSOCK else 'regular-file')
        self._component = self._component_label(path)
        info = path.lstat()
        for parent in (path, *path.parents):
            self._component = self._component_label(parent)
            parent_info = info if parent == path else parent.lstat()
            if stat.S_ISLNK(parent_info.st_mode):
                self._deny('local-symlink', info=parent_info,
                           expected_kind=expected_kind if parent == path else 'directory')
        self._component = self._component_label(path)
        metadata = dict(info=info, expected_mode=mode, expected_kind=expected_kind)
        if not kind(info.st_mode):
            self._deny('local-type', **metadata)
        if info.st_uid != self.uid:
            self._deny('local-owner', **metadata)
        if stat.S_IMODE(info.st_mode) != mode:
            self._deny('local-mode', **metadata)
        if not stat.S_ISDIR(info.st_mode) and info.st_nlink != 1:
            self._deny('local-links', **metadata)
        return info

    def _connect(self):
        if self.sock and self.clock()-self.last_io>=4:self.close()
        if self.sock:return
        if self.clock() < self.retry_at:
            # Preserve a diagnosed access refusal while backing off. A second
            # click must not hide it behind a generic availability message.
            code = 'AUTH_DENIED' if self._diagnostic.get('code') == 'AUTH_DENIED' else 'BROKER_UNAVAILABLE'
            raise BrokerError(code, round((self.retry_at - self.clock()) * 1000))
        revision = self._diagnostic_revision
        try:
            self._checkpoint('filesystem', 'runtime')
            self._private(self.runtime,stat.S_ISDIR,0o700)
            credential=self.runtime/'credential.json'
            self._checkpoint('credential', 'credential')
            info=self._private(credential,stat.S_ISREG,0o600)
            if info.st_size > 4096:
                self._deny('credential-size', info=info)
            fd=os.open(credential,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
            try:
                actual=os.fstat(fd)
                if (actual.st_ino, actual.st_dev) != (info.st_ino, info.st_dev):
                    self._deny('credential-replaced')
                data=decode(os.read(fd,4097))
            finally:os.close(fd)
            if (set(data)!={'protocol','major','boot_id','socket_path','capability'} or data['protocol']!=PROTOCOL
                    or type(data['major']) is not int or data['major']!=1):raise BrokerError('VERSION_UNSUPPORTED')
            identifier(data['boot_id'])
            # Provisioning may select a different runtime, never a frontend path.
            endpoint=self.runtime/'control.sock'
            if data['socket_path'] != str(endpoint):
                self._deny('credential-endpoint-mismatch')
            self._checkpoint('socket-metadata', 'control-socket')
            self._private(endpoint,stat.S_ISSOCK,0o600)
            self._checkpoint('credential', 'credential')
            if not isinstance(data['capability'],str) or len(data['capability'])>128 or len(data['capability'])<32:
                self._deny('credential-format')
            self._checkpoint('socket-connect', 'control-socket')
            self.sock=self.socket_factory(socket.AF_UNIX,socket.SOCK_STREAM); self.sock.settimeout(1.)
            self.sock.connect(str(endpoint))
            if hasattr(socket,'SO_PEERCRED'):
                _,uid,_=struct.unpack('3i',self.sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            elif hasattr(self.sock,'getpeereid'):uid,_=self.sock.getpeereid()
            elif os.uname().sysname=='Darwin':uid=struct.unpack_from('I',self.sock.getsockopt(0,1,80),4)[0]
            else:
                self._deny('peer-credentials-unavailable')
            if uid != self.uid:
                self._deny('peer-owner', observed_uid=uid)
            self.boot=data['boot_id']; self._buffer=b'';self.wire_version=VERSION
            result=self._rpc('hello',dict(capability=data['capability'],client_instance_id=self.instance,supported_versions=['1.2','1.1',VERSION]))
            self.hello=validate_hello(result);self.wire_version=result['negotiated_version']; self.cached=result['state']; self.failures=0; self.retry_at=0.
            self.sock.settimeout(2.)
            self._diagnostic = {'state': 'connected'}
        except (OSError,ValueError,TypeError,KeyError,BrokerError) as error:
            self._failed()
            if isinstance(error, BrokerError):
                if self._diagnostic_revision == revision:
                    self._remember_failure('protocol-rejected', error.code)
                raise
            code = self._io_failure(error) if isinstance(error, OSError) else 'BROKER_UNAVAILABLE'
            if not isinstance(error, OSError):
                self._remember_failure('protocol-rejected', code)
            raise BrokerError(code) from None

    def _failed(self):
        self.close(); self.hello=None
        self.retry_at=self.clock()+[1,2,4,10][min(self.failures,3)]; self.failures+=1

    def _rpc(self,op,args,request_id=None):
        self._checkpoint('hello' if op == 'hello' else 'request', 'control-socket')
        revision = self._diagnostic_revision
        request_id=request_id or uuid4().hex
        wire=VERSION if op=='hello' else self.wire_version
        value=dict(protocol=PROTOCOL,version=wire,request_id=request_id,op=op,args=args)
        if op!='hello':value['boot_id']=self.boot
        raw=encode(value,min(MESSAGE_BYTES,(self.hello or {}).get('limits',{}).get('message_bytes',MESSAGE_BYTES)))
        try:
            deadline=self.clock()+(1 if op=='hello' else 2)
            self.sock.sendall(raw)
            while b'\n' not in self._buffer:
                remaining=deadline-self.clock()
                if remaining<=0:raise TimeoutError()
                self.sock.settimeout(remaining)
                part=self.sock.recv(min(4096,MESSAGE_BYTES+1-len(self._buffer)))
                if not part:raise OSError('disconnected')
                self._buffer+=part
                if len(self._buffer)>MESSAGE_BYTES:raise BrokerError('PROTOCOL_INVALID')
            line,self._buffer=self._buffer.split(b'\n',1); reply=decode(line+b'\n')
            expected={'protocol','version','request_id','boot_id','ok', 'result' if reply.get('ok') is True else 'error'}
            if (set(reply)!=expected or reply.get('protocol')!=PROTOCOL or reply.get('version')!=wire
                    or reply.get('request_id')!=request_id or reply.get('boot_id')!=self.boot
                    or type(reply.get('ok')) is not bool):raise BrokerError('PROTOCOL_INVALID')
            if not reply['ok']:
                failure=reply['error']
                if not isinstance(failure,dict):raise BrokerError('PROTOCOL_INVALID')
                error = BrokerError(failure.get('code'), failure.get('retry_after_ms', 0))
                self._remember_failure('remote-auth-denied' if error.code == 'AUTH_DENIED'
                                       else 'remote-rejected', error.code)
                raise error
            if not isinstance(reply['result'],dict):raise BrokerError('PROTOCOL_INVALID')
            self.last_io=self.clock()
            self._diagnostic = {'state': 'connected'}
            return reply['result']
        except (OSError,ValueError,TypeError,BrokerError) as error:
            if isinstance(error, BrokerError):
                if self._diagnostic_revision == revision:
                    if op in {'acquire_display','player_ready','release_display','tv_started'}:
                        error.uncertain = True
                    self._remember_failure('protocol-rejected', error.code)
                if error.code not in {'PROTOCOL_INVALID','STALE_BOOT','AUTH_DENIED','VERSION_UNSUPPORTED'}:
                    raise
            self._failed()
            if isinstance(error,BrokerError):raise
            # The peer may already have accepted this operation. Never resend it.
            code = self._io_failure(error) if isinstance(error, OSError) else 'BROKER_UNAVAILABLE'
            if not isinstance(error, OSError):
                self._remember_failure('protocol-rejected', code)
            raise BrokerError(code, uncertain=True) from None

    def request(self,op,args):
        with self.lock:
            self._connect()
            deadline=time.monotonic()+2
            while True:
                try:return self._rpc(op,args)
                except BrokerError as error:
                    # Only fixed read/publication calls and an explicit broker
                    # pre-admission rejection. Display and uncertain writes
                    # retain their existing no-retry contract.
                    if (op not in {'operation_status','publish_player_batch','player_status','remove_player'}
                        or error.code!='RATE_LIMITED' or error.uncertain or time.monotonic()>=deadline):raise
                    time.sleep(min(.25,max(.05,error.retry_after_ms/1000)))

    def discover(self,refresh=False):
        with self.lock:
            self._connect()
            if refresh:self.cached=validate_status(self._rpc('status',{}))
            return self.cached

    def status(self):return self.discover(True)

    def register(self,path,collection_id):
        digest(collection_id); path=Path(path)
        with self.lock:
            self._connect(); maximum=self.hello['limits']['max_content_bytes']
            if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=maximum:raise BrokerError('CONTENT_TOO_LARGE')
            fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):raise BrokerError('CONTENT_INVALID')
                with os.fdopen(fd,'rb',closefd=False) as stream:data=stream.read(maximum+1)
            finally:os.close(fd)
            if len(data)>maximum:raise BrokerError('CONTENT_TOO_LARGE')
            if not data.startswith(b'GIF89a'):raise BrokerError('CONTENT_PROFILE_UNSUPPORTED')
            deadline=self.clock()+12
            def admitted(op,args):
                while True:
                    try:return self._rpc(op,args)
                    except BrokerError as error:
                        # Known pre-admission rejection only; never repeat an
                        # uncertain transport result or any display operation.
                        if error.code!='RATE_LIMITED' or error.uncertain or self.clock()>=deadline:raise
                        time.sleep(min(.25,max(.05,error.retry_after_ms/1000)))
            result=admitted('register_content',dict(sha256=hashlib.sha256(data).hexdigest(),size_bytes=len(data),collection_id=collection_id))
            if 'content_id' in result:identifier(result['content_id']);return result
            upload=identifier(result.get('upload_id')); offset=0
            size=min(24576,self.hello['limits']['chunk_bytes'])
            for start in range(0,len(data),size):
                block=data[start:start+size]
                response=admitted('content_chunk',dict(upload_id=upload,offset=offset,data_base64=base64.b64encode(block).decode('ascii')))
                offset+=len(block)
                if response.get('next_offset')!=offset:raise BrokerError('PROTOCOL_INVALID')
            return admitted('commit_content',dict(upload_id=upload))

    def acquire(self,**args):
        result=self.request('acquire_display',args)
        try:
            expected={'lease_id','generation','operation_id','expires_in_ms'}
            if args.get('mode')=='sync':expected.add('alignment_attempt_id')
            if set(result)!=expected:raise BrokerError('PROTOCOL_INVALID')
            identifier(result['lease_id']);identifier(result['operation_id'])
            integer(result['generation'],1);integer(result['expires_in_ms'])
            if 'alignment_attempt_id' in expected:identifier(result['alignment_attempt_id'])
        except (BrokerError,KeyError,TypeError):
            # A malformed success may follow a real acquisition. Reconcile;
            # never treat it as a definitive refusal or resend the mutation.
            raise BrokerError('PROTOCOL_INVALID',uncertain=True) from None
        return result
    def ready(self,**args):return self.request('player_ready',args)
    def renew(self,**args):return self.request('renew_display',args)
    def operation(self,**args):return self.request('operation_status',args)
    def tv_started(self,**args):return self.request('tv_started',args)
    def release(self,**args):return self.request('release_display',args)
    def close(self):
        if self.sock:
            try:self.sock.close()
            except OSError:pass
        self.sock=None; self._buffer=b''
