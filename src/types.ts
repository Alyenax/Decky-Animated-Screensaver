export interface StudioOptions {
  name_display: string; logo_position: string;
  static_fallback: boolean;
  artwork_credit: boolean; cover_credit: boolean; logo_credit: boolean;
  scene_seconds: number;
  shuffle: boolean;
  transition: string;
  show_title: boolean;
  show_logo: boolean;
  show_cover: boolean;
  cover_position: string;
  framing: string;
  reduced_motion: boolean;
  smoothing: boolean;
  smoothing_mode: string;
  smoothing_fps: number;
  max_video_mib: number;
  storage_mib: number;
}
export interface StudioProblem {
  appid:number;name:string;role:'animation'|'cover'|'logo'|'smoothing';code:string;retained_media:boolean;
  skipped?:boolean;
}
export interface StudioGame {
  installed_in_collection?:boolean;
  rank?:number;players?:number;
  collection_member?:boolean;workspace_draft?:boolean;still_mode?:'inherit'|'motion'|'fixed';
  asset?:StudioAsset;cover_asset?:StudioAsset;logo_asset?:StudioAsset;
  problem?:StudioProblem|null;
  branding?: {mode:string;position:string};
  cover_position?:string;
  appid: number;
  name: string;
  installed?: boolean;
  excluded?: boolean;
  manual?: boolean;
  owned?: boolean;
  status: string;
  thumbnail_url?: string;
  skip_reason?: string;
  animated?: boolean;
  width?: number;
  height?: number;
  duration?: number;
  format?: string;
  original_preserved?: boolean;
  pending_change?: boolean;
  error?: string;
  cover_error?: string;
  smoothing_error?: string;
  motion_error?: string;
  logo_error?: string;
  media?: Record<string, string>;
  credits?: { author?: string; source_url?: string };
  crop?: { mode: string; x: number; y: number };
  faceplate_crop?: {x:number;y:number};
  panel_asset?: StudioAsset;
  panel_pending?: boolean;
  panel_manual?: boolean;
}
export interface JsauxState {
  connection_id?: string;
  worker_active?: boolean;
  compatible: boolean;
  detected: boolean;
  configured: boolean;
  enabled: boolean;
  mode: 'sync' | 'async';
  transition: string;
  page_seconds: number;
  framing?: 'square' | 'fill';
  calibration?: {available:boolean;offset_ms:number;saved:boolean;scope:string;last?:{reference_basis?:string;uncertainty_ms?:number;offset_ms?:number;optical?:string}};
  phase: string;
  reason?: string;
  preparation_error?:string;
  controller_status_error?:string;
  connection?: {
    state: string; stage?: string; component?: string; reason?: string; code?: string;
    expected_uid?: number; observed_uid?: number; expected_mode?: string; observed_mode?: string;
    expected_kind?: string; observed_kind?: string; errno?: number;
  } | null;
  prepared?: { ready: boolean; reason?:string;changed?:string[];identity_matches?:boolean;registered?:boolean;file_referenced?:boolean; bytes: number; total_bytes?:number;batch_count?:number;automatic_independent?:boolean;effective_mode?:'sync'|'async'; content_id?: string; percent?: number;pages?:number;frames?:number;estimate_ms?:number;sync_admissible?:boolean;sync_wait_ms?:number;sync_max_bytes?:number;timing_model?:string;transition_steps?:number;transition_optimized?:boolean;orientation?:number;
    power_upgrade_required?:boolean;power_policy?:string|null;power_budget_ppm?:number;peak_load_ppm?:number|null;source_peak_load_ppm?:number|null;power_limited_frames?:number|null };
  hardware?: string;
  retry_after_ms?: number;
  installed?: boolean;
  last_transfer?: string;
  relay_enabled?:boolean;
  relay_transport?:string;
  player_relay?:{kind:string;running:boolean;last_error:string;requests:number;accepted:number;refused:number;preflights:number;last_status:number};
  validation_state?:string;
  alignment_state?:string;
  restore_state?:string;
  first_player_observed?:boolean;
  steam_selection?:string;
  events?: {at:number;event:string;reason:string}[];
}
/** Saved preferences survive disconnection; they are not evidence of hardware. */
export const jsauxVisible = (state?: JsauxState): state is JsauxState => Boolean(state?.detected && state.compatible);
/** Preparation and live display are separate; old backends retain a phase fallback. */
export const jsauxPreparationBusy = (state?: JsauxState) => typeof state?.worker_active==='boolean'
  ? state.worker_active : ['queued','preparing','registering','validating'].includes(state?.phase||'');
/** The settings page observes work; it never starts discovery or conversion by polling. */
export const jsauxBusy = (state?: JsauxState) => jsauxPreparationBusy(state)||[
  'acquiring', 'waiting', 'transferring', 'active', 'restoring', 'releasing',
].includes(state?.phase || '');
/** Bounded, local GIF only. Remote/player addresses cannot enter the preview. */
export function jsauxPreviewURL(value: unknown): string | undefined {
  return typeof value === 'string' && value.length <= 262166 &&
    /^data:image\/gif;base64,[A-Za-z0-9+/]+={0,2}$/.test(value)
    ? value : undefined;
}

export interface UpdateState {
  repository_error?:string;repository_checked_at?:number;
  channel:'stable'|'beta';auto_check:boolean;interval_minutes:number;phase:string;error:string;
  repository:string;
  repository_state?:'unchecked'|'checking'|'ready'|'denied'|'error';
  installed_version:string;available_version:string;available:boolean;checked_at:number;percent:number;confirmation:string;
}
export interface StudioState {
  version?: string;
  display_name_restart_required?: boolean;
  workspace?:{selection_undo?:{count:number;token:string}|null;mode:'collection'|'classic';layout:'comfort'|'compact'|'list';draft_count:number;member_count:number;included_count:number;preview_count?:number;pending_count:number;pending_ids:number[];issues_count:number;skipped_count?:number;skipped_visual_count?:number;installed_count?:number;task:{state:string;error:string;worker_active:boolean;outcome?:'installed'|'unchanged'|'empty';tv_state?:'prepared'|'installed'|'unchanged'|'empty';faceplate_state?:'disabled'|'unavailable'|'prepared'|'installed'|'repair_required';operation?:'prepare'|'install';stage?:'tv'|'faceplate'|'installation'}};
  updates?:UpdateState;
  jsaux?: JsauxState;
  cleanup?: {action:string;files:number;bytes:number}|null;
  name: string;
  revision: string;
  game_count: number;
  installed_count: number;
  ready_count: number;
  included_count?: number;
  failed_count?: number;
  issues_count?: number;
  issues?: StudioProblem[];
  missing_count?: number;
  excluded_count: number;
  key_configured: boolean;
  connection: string;
  storage_bytes: number;
  warning?: string;
  error?: string;
  job: {
    skipped_count?:number;
    worker_active?: boolean;
    state: string;
    stage: string;
    completed: number;
    total: number;
    percent: number;
    current_percent: number | null;
    name?: string;
    appid?: number;
    error?: string;
    queue?: number[];
    history: {
      at: number;
      stage: string;
      percent: number | null;
      appid: number;
      name?: string;
      code?: string;
    }[];
  };
  options: StudioOptions;
  capabilities: { ffmpeg: boolean; ffprobe: boolean; native_first: boolean };
  installation: {
    installed: boolean;
    needs_repair: boolean;
    needs_update?: boolean;
    player_current?: boolean;
    revision?: string;
    name: string;
    error?: string;
    scene_count?: number;
  };
  media_tools: {
    version?: string;
    installation_path?: string;
    installed: boolean;
    available?: boolean;
    state: string;
    percent: number;
    error?: string;
  };
}
export interface StudioPage {
  items: StudioGame[];
  total: number;
  page: number;
  page_size: number;
}
export interface StudioAsset {
  id: number;
  kind: string;
  animated: boolean;
  thumb?: string;
  url?: string;
  width: number;
  height: number;
  author: string;
}
export interface StudioPreview {
  installed?:boolean;
  source_url?:string;source_format?:string;width?:number;height?:number;
  warnings?: {role:string;code:string}[];
  url: string;
  nonce: string;
  count: number;
  revision: string;
}
export type StudioClient = <T = StudioState>(
  action: string,
  payload?: Record<string, unknown>,
) => Promise<T>;
export const studioBusy = (state?: string) =>
  state === "running" || state === "paused_game";
export function studioPreviewURL(value: string): string | undefined {
  try {
    const url = new URL(value);
    if (
      url.protocol === "http:" &&
      url.hostname === "127.0.0.1" &&
      !url.username &&
      !url.password &&
      /^\/[A-Za-z0-9_-]{32,100}\/[a-f0-9]{24}$/.test(url.pathname)
    )
      return url.href;
  } catch {}
  return undefined;
}
