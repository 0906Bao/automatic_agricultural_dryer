// Project-local Home Assistant card. No HACS or third-party card dependency.
class DryerStatusCard extends HTMLElement {
  setConfig(config) {
    if (!Array.isArray(config.entities)) throw new Error('entities must be an array');
    this.config = config;
    if (!this.shadowRoot) this.attachShadow({mode: 'open'});
    this.build();
    this.update();
  }

  set hass(value) {
    this._hass = value;
    this.setAttribute('data-theme', value?.themes?.darkMode === false ? 'light' : 'dark');
    this.update();
  }
  getCardSize() { return 1 + (this.config?.entities.length || 0); }

  presentation(row) {
    const states = this._hass?.states || {};
    const entity = states[row.entity];
    const source = states[row.state_entity || row.entity];
    const offline = states['binary_sensor.dryer_online']?.state !== 'on';
    const missing = !entity || !source || [entity.state, source.state].some(s => ['unknown', 'unavailable'].includes(s));
    let color = offline || missing ? 'neutral' : row.colors?.[source.state] || row.default_color || 'info';
    // Older firmware reports NORMAL while still holding closed for safe time.
    if (!offline && !missing && row.state_entity === 'sensor.dryer_cover_reason' &&
        source.state === 'NORMAL' && states['sensor.dryer_cover_request']?.state === 'CLOSE') color = 'warning';
    let text = entity?.state || 'Chưa có dữ liệu';
    if (offline) text = row.state_entity === 'binary_sensor.dryer_online' ? 'Mất kết nối' : 'Mất kết nối · chưa xác nhận';
    else if (missing) text = 'Chưa có dữ liệu';
    else if (entity.attributes?.unit_of_measurement) {
      const number = Number(entity.state);
      text = `${Number.isFinite(number) ? new Intl.NumberFormat('vi-VN', {maximumFractionDigits: 1}).format(number) : entity.state} ${entity.attributes.unit_of_measurement}`;
    }
    const icon = row.state_icons?.[source?.state] || row.icon || entity?.attributes?.icon || 'mdi:information-outline';
    return {color, text, icon: offline && row.state_entity === 'binary_sensor.dryer_online' ? 'mdi:lan-disconnect' : icon};
  }

  build() {
    const root = this.shadowRoot;
    root.replaceChildren();
    const style = document.createElement('style');
    style.textContent = `
      :host{display:block;--dryer-success:#66bb6a;--dryer-warning:#ffb74d;--dryer-danger:#ef5350;--dryer-info:#4fc3f7;--dryer-neutral:var(--secondary-text-color,#9e9e9e)}
      :host([data-theme=light]){--dryer-success:#2e7d32;--dryer-warning:#a66100;--dryer-danger:#c62828;--dryer-info:#0277bd}
      ha-card{overflow:hidden}
      h2{font:var(--ha-card-header-font-family,inherit);font-size:var(--ha-card-header-font-size,24px);font-weight:400;line-height:32px;padding:20px 20px 12px;margin:0;color:var(--ha-card-header-color,var(--primary-text-color))}
      .rows{padding:0 12px 12px}
      button{display:grid;grid-template-columns:40px minmax(0,1fr) minmax(100px,1.15fr);align-items:center;gap:10px;width:100%;min-height:54px;padding:10px 8px;border:0;border-radius:8px;background:none;color:var(--primary-text-color);font:inherit;text-align:left;cursor:pointer}
      button:hover,button:focus-visible{background:var(--secondary-background-color);outline:2px solid var(--divider-color);outline-offset:-2px}
      .badge{width:36px;height:36px;display:flex;align-items:center;justify-content:center;border-radius:10px;background:color-mix(in srgb,currentColor 13%,transparent)}
      ha-icon{--mdc-icon-size:23px}
      .name{font-size:14px;line-height:1.45;overflow-wrap:anywhere}
      .state{font-size:14px;font-weight:600;line-height:1.45;text-align:right;overflow-wrap:anywhere}
      .success{color:var(--dryer-success)}.warning{color:var(--dryer-warning)}.danger{color:var(--dryer-danger)}.info{color:var(--dryer-info)}.neutral{color:var(--dryer-neutral)}
      .legend{display:flex;gap:12px;flex-wrap:wrap;padding:0 20px 16px;font-size:12px;color:var(--secondary-text-color)}
      .dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:4px;background:currentColor}
      @media(max-width:400px){button{grid-template-columns:36px minmax(0,1fr) minmax(90px,1fr);gap:8px}.name,.state{font-size:13px}}
    `;
    root.append(style);
    const card = document.createElement('ha-card');
    const heading = document.createElement('h2'); heading.textContent = this.config.title || '';
    card.append(heading);
    const rows = document.createElement('div'); rows.className = 'rows';
    this.rowElements = this.config.entities.map(row => {
      const button = document.createElement('button'); button.type = 'button';
      const badge = document.createElement('span'); badge.className = 'badge';
      const icon = document.createElement('ha-icon'); badge.append(icon);
      const name = document.createElement('span'); name.className = 'name'; name.textContent = row.name || row.entity;
      const state = document.createElement('span'); state.className = 'state';
      button.append(badge, name, state);
      button.addEventListener('click', () => this.dispatchEvent(new CustomEvent('hass-more-info', {
        detail: {entityId: row.entity}, bubbles: true, composed: true
      })));
      rows.append(button);
      return {row, button, badge, icon, name, state};
    });
    card.append(rows);
    if (this.config.legend) {
      const legend = document.createElement('div'); legend.className = 'legend';
      for (const [color, label] of [['success','Bình thường'],['warning','Cảnh báo / chờ'],['danger','Nguy hiểm / lỗi'],['neutral','Không xác nhận']]) {
        const item = document.createElement('span');
        const dot = document.createElement('span'); dot.className = `dot ${color}`;
        item.append(dot, document.createTextNode(label)); legend.append(item);
      }
      card.append(legend);
    }
    root.append(card);
  }

  update() {
    if (!this.config || !this._hass) return;
    for (const entry of this.rowElements || []) {
      const view = this.presentation(entry.row);
      entry.badge.className = `badge ${view.color}`;
      entry.state.className = `state ${view.color}`;
      entry.icon.setAttribute('icon', view.icon);
      entry.state.textContent = view.text;
      entry.button.setAttribute('aria-label', `${entry.name.textContent}: ${view.text}`);
    }
  }
}

if (!customElements.get('dryer-status-card')) customElements.define('dryer-status-card', DryerStatusCard);
window.customCards = window.customCards || [];
window.customCards.push({type:'dryer-status-card',name:'Giàn phơi · trạng thái',description:'Biểu tượng và màu trạng thái từ dữ liệu ESP32.'});
