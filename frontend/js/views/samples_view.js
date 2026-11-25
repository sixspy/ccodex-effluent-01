export const samplesViewTemplate = `
  <div class="grid-2">
    <div class="panel">
      <h3>采样批次（正式排放册）</h3>
      <table>
        <thead><tr><th>编号</th><th>口</th><th>许可</th><th>流量</th><th>状态</th><th>代</th></tr></thead>
        <tbody>
          <tr v-for="s in samples" :key="s.id" @click="loadSample(s.id)" style="cursor:pointer">
            <td>{{ s.sample_code }}</td><td>{{ s.outfall_code }}</td><td>{{ s.permit_ref }}</td>
            <td>{{ s.flow_m3h }}</td><td :class="sampleClass(s.status)">{{ s.status }}</td>
            <td>{{ s.generation }}</td>
          </tr>
        </tbody>
      </table>
      <p class="footnote">
        检修期采样不入此册（一律拒收封存，见处理厂页拍板说明）；检修前历史批次照常列示，
        不计入检修期对账流量。
      </p>
      <div v-if="sampleDetail" class="panel" style="margin-top:0.8rem;border-style:dashed">
        <h3>批次详情</h3>
        <div class="kv">
          <span>指标</span><span>{{ fmtMetrics(sampleDetail.sample.metrics) }}</span>
          <span>挂起</span><span>{{ sampleDetail.exceed_holds.length }}</span>
          <span>准排</span><span>{{ sampleDetail.discharge_releases.length }}</span>
          <span>封批</span><span>{{ sampleDetail.discharge_seals.length }}</span>
        </div>
      </div>
    </div>
    <div class="panel">
      <h3>入库采样</h3>
      <div class="form-row"><div>
        <label>排放口</label>
        <select v-model.number="sampleForm.outfall_id">
          <option v-for="o in outfalls" :key="o.id" :value="o.id">
            {{ o.outfall_code }} · {{ o.plant_code }}<template v-if="o.is_maintenance">（检修禁采）</template>
          </option>
        </select>
      </div>
      <div><label>许可号</label><input v-model="sampleForm.permit_ref"/></div></div>
      <div v-if="samplingBlocked" class="banner err" style="margin-top:0.6rem">
        检修禁采：所选排放口所属厂检修中，新建采样按钮已禁用（与处理厂页检修灯同屏互斥）。
      </div>
      <div class="form-row">
        <div><label>COD</label><input type="number" v-model.number="sampleForm.cod"/></div>
        <div><label>氨氮</label><input type="number" v-model.number="sampleForm.nh3n"/></div>
      </div>
      <div class="form-row">
        <div><label>总磷</label><input type="number" v-model.number="sampleForm.tp"/></div>
        <div><label>流量 m3/h</label><input type="number" v-model.number="sampleForm.flow_m3h"/></div>
      </div>
      <label>编号（可空自动）</label><input v-model="sampleForm.sample_code"/>
      <div class="actions">
        <button :disabled="samplingBlocked" @click="createSample">入库</button>
      </div>
    </div>
  </div>`;
