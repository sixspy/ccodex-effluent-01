export const plantsViewTemplate = `
  <div class="grid-2">
    <div class="panel">
      <h3>处理厂</h3>
      <table>
        <thead><tr><th>编码</th><th>名称</th><th>流域</th><th>设计量</th><th>状态</th><th>口数</th></tr></thead>
        <tbody>
          <tr v-for="p in plants" :key="p.id" @click="loadPlant(p.id)" style="cursor:pointer">
            <td>{{ p.plant_code }}</td><td>{{ p.name }}</td><td>{{ p.basin }}</td>
            <td>{{ p.design_cap_m3d }}</td>
            <td :class="statusClass(p.status)">
              <span v-if="p.is_maintenance" class="maint-lamp" title="检修禁采">● 检修灯</span>
              <span v-else>{{ p.status }}</span>
            </td>
            <td>{{ p.outfall_count }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel">
      <h3>新建处理厂</h3>
      <div class="form-row"><div><label>编码</label><input v-model="plantForm.plant_code"/></div>
      <div><label>名称</label><input v-model="plantForm.name"/></div></div>
      <div class="form-row"><div><label>流域</label><input v-model="plantForm.basin"/></div>
      <div><label>设计量 m3/d</label><input type="number" v-model.number="plantForm.design_cap_m3d"/></div></div>
      <div class="actions"><button @click="createPlant">登记</button></div>
      <div v-if="plantDetail" style="margin-top:1rem">
        <h3>详情 {{ plantDetail.plant.plant_code }}</h3>
        <div class="kv">
          <span>名称</span><span>{{ plantDetail.plant.name }}</span>
          <span>厂态</span>
          <span :class="plantDetail.plant.is_maintenance ? 'warn' : 'pass'">
            {{ plantDetail.plant.status }}
            <template v-if="plantDetail.plant.is_maintenance"> · 检修禁采灯亮</template>
          </span>
          <span>采样写口</span>
          <span :class="plantDetail.plant.sampling_blocked ? 'fail' : 'pass'">
            {{ plantDetail.plant.sampling_blocked ? "已封死（检修禁采）" : "开放" }}
          </span>
          <span>排放口</span><span>{{ plantDetail.outfalls.length }}</span>
          <span>许可</span><span>{{ plantDetail.permits.length }}</span>
        </div>
        <div class="actions">
          <button class="warn" @click="setPlantStatus(plantDetail.plant.id, '检修')">转检修（禁采）</button>
          <button class="secondary" @click="setPlantStatus(plantDetail.plant.id, '运行')">恢复运行</button>
        </div>
        <p v-if="plantDetail.plant.is_maintenance" class="footnote">
          检修灯亮即采样页新建按钮同步禁用；正式排放册、对账流量与排放口当日曲线均剔除本厂批次。
        </p>
      </div>
      <div v-if="maintDecisions.length" class="panel" style="margin-top:0.9rem;border-style:dashed">
        <h3>检修禁采拍板说明</h3>
        <table>
          <thead><tr><th>厂</th><th>拍板时间</th><th>当日封死</th><th>说明</th></tr></thead>
          <tbody>
            <tr v-for="d in maintDecisions" :key="d.id">
              <td>{{ d.plant_code }}</td><td>{{ d.decided_at }}</td><td>{{ d.sealed_on }}</td>
              <td>{{ d.decision }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>`;
