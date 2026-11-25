export const dashboardViewTemplate = `
  <section class="hero-strip">
    <h2>污水排放批总览</h2>
    <p>采样入库 → 超标挂起 → 准排裁定 → 封批升代 → 许可对账</p>
  </section>
  <div class="stats">
    <div class="stat"><div class="n">{{ dash.plants || 0 }}</div><div class="l">处理厂</div></div>
    <div class="stat" :class="{warn: dash.maintenance_plants}">
      <div class="n">{{ dash.maintenance_plants || 0 }}</div><div class="l">检修禁采厂</div>
    </div>
    <div class="stat"><div class="n">{{ dash.outfalls || 0 }}</div><div class="l">排放口</div></div>
    <div class="stat"><div class="n">{{ dash.samples || 0 }}</div><div class="l">正式采样批次</div></div>
    <div class="stat"><div class="n">{{ dash.maintenance_drafts || 0 }}</div><div class="l">检修拒收草稿</div></div>
    <div class="stat"><div class="n">{{ dash.open_exceeds || 0 }}</div><div class="l">开放超标</div></div>
    <div class="stat"><div class="n">{{ dash.discharge_releases || 0 }}</div><div class="l">已准排</div></div>
    <div class="stat"><div class="n">{{ dash.discharge_seals || 0 }}</div><div class="l">已封批</div></div>
    <div class="stat"><div class="n">{{ dash.permits || 0 }}</div><div class="l">许可册</div></div>
    <div class="stat"><div class="n">{{ dash.side_pending || 0 }}</div><div class="l">旁路挂起</div></div>
  </div>
    <div class="panel">
      <h3>检修禁采同源核销</h3>
      <div class="kv">
        <span>检修厂计数（总览）</span>
        <span :class="dash.maintenance_plants ? 'warn' : 'pass'">{{ dash.maintenance_plants || 0 }}</span>
        <span>处理厂服务检修态</span>
        <span :class="dash.maintenance_plants ? 'warn' : 'pass'">{{ (dash.maintenance_plant_codes || []).join("、") || "无" }}</span>
        <span>检修拍板盘数</span><span>{{ dash.maintenance_decisions || 0 }}</span>
        <span>拒收封存草稿</span><span>{{ dash.maintenance_drafts || 0 }}</span>
      </div>
      <p class="footnote">总览检修计数与处理厂服务 status 字段同值；检修期采样只落拒收封存草稿，正式册与对账流量零增。</p>
    </div>
    <div class="panel">
      <h3>产品骨架</h3>
      <p class="muted">{{ (dash.meta && dash.meta.skeleton) || "—" }}</p>
    </div>`;
