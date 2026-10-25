// Decky-scoped product styles; no Steam-wide focus/input overrides.
export const COLLECTION_CSS=`
.collection-frame{height:100%;min-height:0;min-width:0;background:var(--gpSystemDarkestGrey,#0e141b);color:var(--gpSystemLightestGrey,#dcdedf);font:inherit;--collection-space-xs:8px;--collection-space-sm:12px;--collection-space-md:16px;--collection-space-lg:24px;--collection-radius:2px}
.collection-tab-host{height:100%;min-height:0;min-width:0}
.collection-content{box-sizing:border-box;min-width:0;margin:0 auto;max-width:1300px}
.collection-content h2{font-size:20px;font-weight:500;line-height:24px;margin:0 0 16px}
.collection-content p{font-size:14px;line-height:20px;color:var(--gpSystemLighterGrey,#b8bcbf)}
.collection-scroll-owner{min-width:0}
.collection-nested-scroll{height:100%;overflow:hidden}
.collection-nested-scroll>div{height:100%;min-height:0}
.collection-nested-scroll .collection-content{padding:16px var(--gpSpace-Gutter,2.8vw) 40px}
.collection-workflow{margin-bottom:16px}
.collection-more-trigger{display:flex;justify-content:flex-end;margin-top:8px}

.collection-faceplate{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:12px 0;padding:12px;box-sizing:border-box}
.collection-faceplate>span{flex:1 1 240px}
.collection-grid .collection-card.collection-card-alert small{color:#e5ae64}
.collection-grid .collection-card.collection-card-pending small{color:var(--gpStoreBlue,#1a9fff)}


.collection-tab-host{display:flex;flex-direction:column;min-height:0;overflow:clip;contain:layout}.collection-tab-host>div{flex:1;min-height:0;max-height:100%;height:100%}
.collection-grid .collection-card.collection-candidate .collection-picture{aspect-ratio:460/215;height:auto;position:relative;background:#09121c}
.collection-grid .collection-candidate .collection-picture img,.collection-grid .collection-candidate .collection-picture canvas{object-fit:contain;width:100%;height:100%;position:absolute;inset:0;aspect-ratio:auto}
.candidate-artwork{display:block;position:relative;aspect-ratio:460/215;overflow:hidden;background:#09121c}.collection-grid .collection-candidate .candidate-artwork .candidate-motion{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;aspect-ratio:auto;pointer-events:none}.candidate-animation-state{position:absolute;bottom:4px;left:4px;right:56px;background:#09121cce;color:#eef4fa;padding:4px 6px;font-size:12px;pointer-events:none}.candidate-placeholder{display:grid;place-content:center;padding:12px;box-sizing:border-box;font-size:14px}.collection-grid .collection-card .candidate-animation-badge{position:absolute;bottom:4px;right:4px;padding:2px 6px;border-radius:4px;background:#09121cce;color:white;font-size:12px;pointer-events:none}
.collection-detail>[data-detail-column]{min-width:0}.collection-detail [data-detail-column="settings"]>.collection-actions{gap:12px;margin:16px 0}
.collection-frame .collection-card{padding:0;text-align:left;border-radius:0;min-width:0;box-sizing:border-box;position:relative;line-height:1.35}
.collection-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:16px 0}.collection-grid.compact{grid-template-columns:repeat(5,minmax(0,1fr))}.collection-grid.list{display:flex;flex-direction:column;gap:12px}
.collection-game-media{min-width:0;position:relative}.collection-game-media>.collection-picture{height:0;padding-bottom:46.73913%;aspect-ratio:auto}
.collection-game-media .collection-picture>img,.collection-game-media .collection-picture>canvas{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.collection-game-copy{min-width:0;flex:1;box-sizing:border-box;padding:8px 12px}
.collection-game-copy strong{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:500}
.collection-game-copy small{display:block;padding-top:4px;font-size:16px;color:var(--gpSystemLighterGrey,#b8bcbf);overflow-wrap:anywhere}
.collection-game-copy .collection-rank{padding:0 0 4px}
.collection-grid.list .collection-card,.collection-grid.list .collection-select-main{display:flex;align-items:center;gap:16px;width:100%;min-width:0}
.collection-grid.list .collection-game-media{flex:0 0 135px;width:135px}
.collection-grid.list .collection-game-copy{padding:8px 0}.collection-grid.list .collection-select-main .collection-game-copy{padding-right:44px}.collection-grid.list .collection-game-copy strong{white-space:normal;overflow-wrap:anywhere}
.collection-grid.list .collection-select-main{flex:1;align-self:stretch}.collection-grid.list .collection-customize{flex:0 0 180px;width:180px!important;align-self:center}
.collection-grid:not(.list) .collection-select-card{display:flex;flex-direction:column}.collection-grid:not(.list) .collection-select-main{flex:1}
.collection-candidate>strong,.collection-candidate>small{display:block;padding:8px 12px;overflow-wrap:anywhere}
.collection-placeholder{display:grid;place-content:center;aspect-ratio:460/215;background:#243a4b;color:#c6b1ef;font-size:20px;overflow-wrap:anywhere;text-align:center;padding:15px}
.collection-actions{display:flex;align-items:center;gap:var(--collection-space-sm);flex-wrap:wrap;margin:var(--collection-space-md) 0}.collection-actions button{flex:1;min-height:44px}
.collection-detail{display:grid;grid-template-columns:minmax(0,1fr) minmax(380px,.9fr);gap:28px}.collection-detail-image{width:100%;max-height:320px;object-fit:contain;background:#0b1420}.collection-detail .collection-placeholder{max-height:320px}
.collection-field{display:flex;gap:18px;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--gpBackground-LightSofter,rgba(255,255,255,.1));min-height:60px}.collection-field small{display:block;font-size:16px;color:#bdcad7}.collection-field button{min-height:44px}
.collection-chosen-thumb{width:72px;height:44px;object-fit:contain;flex-shrink:0;background:#0b1420}.collection-field>div{flex:1;min-width:0;overflow-wrap:anywhere}
.collection-frame .collection-field{display:grid;grid-template-columns:minmax(160px,1fr) auto auto;gap:12px;align-items:center;min-height:66px}
.collection-frame .collection-background-field{grid-template-columns:minmax(0,1fr) auto}.collection-background-actions{grid-column:1/-1;display:flex;gap:12px;min-width:0}.collection-frame .collection-background-actions>.collection-action{flex:1 1 0!important;width:auto!important;min-width:0!important}.collection-still-option{margin:12px 0}
.collection-frame .collection-field .collection-label{min-width:160px;overflow-wrap:break-word;word-break:normal;white-space:normal}
.collection-frame .collection-field>.collection-action{grid-column:3;width:120px!important;min-width:100px!important;max-width:140px!important;justify-self:end;flex:none!important}
.collection-frame .collection-action{width:auto!important;min-width:100px!important;display:inline-flex!important;align-items:center;justify-content:center;flex:none;word-break:normal;overflow-wrap:break-word}
.collection-frame [data-collection-focus="back"]{width:112px!important;max-width:112px!important;margin-bottom:8px!important}
.collection-frame .collection-actions>.collection-action{flex:1 1 140px!important;width:auto!important}
.collection-picture{display:block;position:relative;aspect-ratio:460/215;background:#101c2b;overflow:hidden}
.collection-picture>img{display:block;width:100%;height:100%;object-fit:cover}
.collection-picture>canvas{width:100%;height:100%;object-fit:contain}
.collection-picture>span{position:absolute;inset:0;display:grid;place-content:center;padding:14px;color:var(--gpSystemLighterGrey,#b8bcbf);font-size:16px;text-align:center}
.collection-chosen-thumb.collection-picture{width:72px;height:44px;aspect-ratio:auto}
.collection-render{position:relative;overflow:hidden;background:#0b1420;isolation:isolate}
.collection-sheet-preview{padding:0;margin:0;min-width:0}.collection-sheet-preview>.box{margin-top:0}
.collection-render .collection-picture{width:100%;max-height:300px}.collection-render .collection-picture img{object-fit:contain}
.collection-crop-guide{position:absolute;width:76%;max-height:85%;border:2px solid #91edf2;box-shadow:0 0 0 400px #0005;pointer-events:none}
.collection-logo-guide{position:absolute;bottom:12px;left:14px;color:white;text-shadow:0 2px 4px black;pointer-events:none;font-size:16px}
.collection-logo-guide .collection-picture{width:130px;height:60px;aspect-ratio:auto;background:transparent}.collection-logo-guide .collection-picture img{object-fit:contain}
.collection-rank{display:block;padding:6px 12px 0;color:#91edf2;font-size:15px}
.collection-settings-form{width:100%;max-width:none;margin:var(--collection-space-md) 0 0;min-width:0;box-sizing:border-box}.collection-settings-form>*{min-width:0}.collection-settings-form details{margin:var(--collection-space-lg) 0;border-top:1px solid var(--gpBackground-LightSofter,rgba(255,255,255,.1));padding-top:var(--collection-space-md)}.collection-settings-form summary{padding:var(--collection-space-sm) 0}.collection-settings-form pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;max-height:240px;overflow:auto}
.collection-frame [data-updates-panel]{width:100%;min-width:0;margin-top:var(--collection-space-md);box-sizing:border-box}
.collection-settings-form>.collection-action{display:flex!important;width:100%!important;margin:10px 0!important}
@media(max-width:700px){.collection-frame .collection-field{grid-template-columns:minmax(140px,1fr) auto}.collection-frame .collection-field>.collection-action{grid-column:2}.collection-chosen-thumb{display:none}.collection-frame .collection-field .collection-label{min-width:140px}}
.collection-settings{display:flex;flex-direction:column;gap:var(--collection-space-sm);width:100%;max-width:none}.collection-settings>button{text-align:left!important;min-height:54px!important}
.collection-attention{display:flex;align-items:center;flex-wrap:wrap;gap:var(--collection-space-sm) var(--collection-space-md);padding:var(--collection-space-md);margin:var(--collection-space-md) 0;box-sizing:border-box;width:100%}.collection-attention>strong{flex:1 1 220px}.collection-attention>p{flex-basis:100%;margin:0}.collection-frame .collection-attention>.collection-action{min-width:180px!important;min-height:44px!important;max-width:100%!important}.collection-empty{text-align:center;padding:36px 20px}
.das .collection-player{width:100%;max-width:640px;margin:16px auto;box-sizing:border-box}.das .collection-sheet-preview>.collection-player{margin:0 auto}.collection-player-stage{position:relative;height:0;padding-bottom:56.25%;overflow:hidden}.collection-frame .collection-player-stage .player,.collection-player-stage .player{position:absolute;inset:0;display:block;width:100%;height:100%;margin:0;border:0;aspect-ratio:auto}.collection-player-controls{display:flex;flex-wrap:nowrap;gap:12px;margin-top:12px;min-width:0}.collection-player-controls>button{box-sizing:border-box;white-space:normal}.collection-quick-note{font-size:14px;color:#c2d3df}

.collection-order{min-width:0;width:100%}.collection-order [data-order-id]{display:block;overflow-wrap:anywhere}.collection-order-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:56px}.collection-order-heading h2{margin:16px 0}.collection-order-heading [role=status]{font-size:14px;min-height:22px}
.collection-detail>[data-detail-column]{display:flex;flex-direction:column;gap:16px}
.collection-detail>[data-detail-column]>.collection-actions{margin:0}
.collection-panel-editor{display:flex;flex-direction:column;gap:16px;margin:16px 0 24px;max-width:640px}
.collection-panel-editor h3{margin:0;font-size:18px;font-weight:500}
.collection-panel-preview{width:256px;aspect-ratio:64/54;background:#000;overflow:hidden;align-self:center;position:relative}
.collection-panel-preview>.collection-picture{position:absolute;inset:0;width:100%;height:100%;aspect-ratio:auto;background:#000}
.collection-panel-preview .collection-picture>img,.collection-panel-preview .collection-picture>canvas{object-fit:contain;object-position:center;image-rendering:pixelated}
.collection-panel-preview.is-fill .collection-picture>img,.collection-panel-preview.is-fill .collection-picture>canvas{object-fit:cover;object-position:50% var(--panel-crop-y,50%)}
.collection-panel-editor [data-faceplate-crop]{margin:0;min-width:0}
.collection-panel-editor .collection-action{align-self:stretch;max-width:100%}

/* Alpha51: accessible collection-density control, scoped to the Studio only. */
.collection-search-view{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;align-items:start;min-width:0;margin:16px 0}
.collection-search-view>*{min-width:0}
.collection-view-picker{min-width:0}
.collection-grid .collection-card small{overflow-wrap:anywhere}
.collection-unsaved{border-left:3px solid #e5ae64;padding:10px 12px;color:#ffe2a9!important}
.collection-draft-hint{font-size:14px!important}

@media(max-width:1100px){.collection-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.collection-grid.compact{grid-template-columns:repeat(4,minmax(0,1fr))}.collection-detail{grid-template-columns:1fr}.collection-detail-image{max-height:280px}.collection-grid.list{grid-template-columns:1fr}}
@media(max-width:700px){.collection-content{padding:16px}.collection-grid,.collection-grid.compact{grid-template-columns:repeat(2,minmax(0,1fr))}.collection-grid.list .collection-game-media{flex-basis:90px;width:90px}.collection-grid.list .collection-customize{flex-basis:140px;width:140px!important}.collection-detail{min-width:0}}

/* Only artwork/structural geometry: native Steam controls retain their paint. */
.collection-toolbar-field{min-width:0;align-self:stretch}.collection-toolbar-label{display:block;font-size:14px;line-height:20px;margin-bottom:8px}
.collection-toolbar-field .DialogInputLabelGroup{margin:0}
.collection-toolbar-field input,.collection-toolbar-field .DialogDropDown{box-sizing:border-box;width:100%;min-height:48px}
.collection-toolbar-field .DialogDropDown button{width:100%;min-height:48px;white-space:normal}
.collection-inclusion{margin:16px 0}
.collection-select-main{position:relative;min-width:0;cursor:pointer}
.collection-selection-check{position:absolute;top:8px;right:8px;width:24px;height:24px;display:grid;place-items:center;background:var(--gpSystemDarkestGrey,#0e141b);border:2px solid var(--gpSystemLightestGrey,#dcdedf)}
.collection-select-card.is-selected .collection-selection-check{background:var(--gpStoreBlue,#1a9fff);color:white}
.collection-select-card.is-selected .collection-select-main{outline:2px solid var(--gpStoreBlue,#1a9fff);outline-offset:-2px}
.collection-customize{width:100%!important;min-width:0!important;white-space:normal;overflow-wrap:anywhere;box-sizing:border-box}
.collection-selection-summary{margin-bottom:24px}
.collection-load-more{display:flex;gap:16px;justify-content:space-between;align-items:center;margin:16px 0}

.faceplate-preparation-status{margin:12px 0 20px}
.faceplate-preparation-status p{margin:4px 0}
.gca-check-feedback[data-state="unavailable"]{color:#f3b560}

/* Recovery/confirmation retain native paint; equal rows remove Back's page-only margin. */
.collection-frame .collection-faceplate-recovery{padding:0;margin:16px 0;width:100%}
.collection-frame .collection-faceplate-recovery .collection-actions,.collection-frame .collection-confirm .collection-actions{align-items:stretch}
.collection-frame .collection-faceplate-recovery .collection-action,.collection-frame .collection-confirm .collection-action{height:auto;white-space:normal;max-width:100%;align-self:stretch}
.collection-frame .collection-confirm [data-collection-focus="back"]{margin-bottom:0!important}
.faceplate-preparation-title.is-ready{color:var(--gpColor-Green,#a4d007)}
.faceplate-preparation-title.has-issue,.collection-faceplate-recovery>p{color:#f3b560}
.collection-faceplate-recovery[data-faceplate-recovery="sync-capacity"]>p,.collection-faceplate-recovery[data-faceplate-recovery="capacity"]>p{color:inherit}
.collection-frame .collection-management-actions{display:flex;justify-content:flex-end;gap:12px;flex-wrap:wrap;margin:10px 0 18px}
.collection-frame .collection-management-actions .collection-action{width:auto!important;flex:0 1 auto;min-width:180px!important}
.collection-frame .collection-selection-undo{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:14px 0;margin:0 0 12px;border-bottom:1px solid #ffffff20;color:#b8bcbf}
.collection-frame .collection-selection-undo p{margin:0;flex:1;min-width:180px}
.collection-frame .collection-selection-undo .collection-action{width:auto!important;min-width:130px!important}
.collection-frame .collection-management-confirm{max-width:760px;margin:18px 0}
.collection-frame .collection-management-confirm h2{font-size:26px;margin:0 0 18px}
.collection-frame .collection-management-confirm p{line-height:1.5;color:#b8bcbf}
.collection-frame .collection-management-confirm .collection-actions{margin-top:24px}
.collection-frame .collection-management-confirm .collection-action{width:auto!important;min-width:180px!important}
`;
