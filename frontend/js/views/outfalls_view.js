export const outfallsViewTemplate = `
  <div class="grid-2">
    <div class="panel">
      <h3>排放口限值</h3>
      <table>
        <thead><tr><th>编码</th><th>厂</th><th>河段</th><th>COD</th><th>氨氮</th><th>总磷</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="o in outfalls" :key="o.id" @click="loadOutfall(o.id)" style="cursor:pointer">
            <td>{{ o.outfall_code }}</td><td>{{ o.plant_code }}</td><td>{{ o.river_reach }}</td>
            <td>{{ o.cod_limit }}</td><td>{{ o.nh3n_limit }}</td><td>{{ o.tp_limit }}</td>
            <td :class="statusClass(o.status)">
              <span v-if="o.is_maintenance" class="maint-lamp">● 检修</span>
              <span v-else>{{ o.status }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="footnote">检修厂排放口当日曲线一律剔除该厂批次，不并入排口流量。</p>
      <div v-if="outfallDetail" class="panel" style="margin-top:0.8rem;border-style:dashed">
        <h3>当日曲线 {{ outfallDetail.outfall.outfall_code }}</h3>
        <div class="kv">
          <span>厂态</span>
          <span :class="outfallDetail.outfall.is_maintenance ? 'warn' : 'pass'">
            {{ outfallDetail.outfall.plant_status || (outfallDetail.outfall.is_maintenance ? "检修" : "运行") }}
          </span>
          <span>检修剔除</span><span>{{ outfallDetail.maintenance_excluded || 0 }}</span>
          <span>曲线点数</span><span>{{ outfallDetail.daily_curve.length }}</span>
        </div>
        <p v-if="outfallDetail.outfall.is_maintenance" class="banner err" style="margin-top:0.6rem">
          检修厂排放口：当日曲线已整段剔除，不计任何批次流量。
        </p>
        <table v-else>
          <thead><tr><th>采样</th><th>流量 m3/h</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="p in outfallDetail.daily_curve" :key="p.sample_code">
              <td>{{ p.sample_code }}</td><td>{{ p.flow_m3h }}</td><td>{{ p.status }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div class="panel">
      <h3>新建排放口</h3>
      <div class="form-row"><div><label>编码</label><input v-model="outfallForm.outfall_code"/></div>
      <div><label>处理厂 ID</label><input type="number" v-model.number="outfallForm.plant_id"/></div></div>
      <label>河段</label><input v-model="outfallForm.river_reach"/>
      <div class="form-row">
        <div><label>COD 限</label><input type="number" v-model.number="outfallForm.cod_limit"/></div>
        <div><label>氨氮限</label><input type="number" v-model.number="outfallForm.nh3n_limit"/></div>
      </div>
      <label>总磷限</label><input type="number" v-model.number="outfallForm.tp_limit"/>
      <div class="actions"><button @click="createOutfall">登记</button></div>
    </div>
  </div>`;
