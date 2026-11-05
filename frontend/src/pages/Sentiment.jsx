import { useCallback, useMemo, useState } from 'react';
import { Activity, MessageSquare, TrendingDown, Users } from 'lucide-react';
import FilterBar from '../components/FilterBar';
import PageHeader from '../components/PageHeader';
import KeyTakeaways from '../components/KeyTakeaways';
import PinnedAnswers from '../components/PinnedAnswers';
import Metric from '../components/Metric';
import Panel from '../components/Panel';
import EChart from '../components/EChart';
import { LowResponseBadge } from '../components/Badges';
import { useFilters } from '../context/FilterContext';
import { useTheme } from '../context/ThemeContext';
import { useApi } from '../lib/api';
import { useIsMobile } from '../lib/useMedia';
import { fmtInt, fmtPct, fmtSigned, isNum } from '../lib/format';
import {
  driversOption, dumbbellOption, exitsOption, heatmapOption, mixOption, nonResponseOption, quadrantOption, themesOption,
} from './sentimentCharts';

const DIMS = [
  ['thread', 'Thread'], ['function', 'Function'], ['job_family', 'Job family'], ['grade', 'Grade'], ['location', 'Location'],
  ['tenure_band', 'Tenure'], ['compa_band', 'Compa band'], ['manager_status', 'Manager status'], ['performance_rating', 'Rating'],
];

export default function Sentiment() {
  const { filters, drill } = useFilters();
  const { palette: p } = useTheme();
  const mobile = useIsMobile();
  const [dim, setDim] = useState('thread');
  const [hmWave, setHmWave] = useState('Oct');

  const kpis = useApi('/enps/kpis', { filters });
  const panel = useApi('/enps/panel', { filters });
  const byWave = useApi('/enps/by-wave', { filters });
  const seg = useApi('/enps/segment', { filters, params: { dim } });
  const drivers = useApi('/enps/drivers', { filters });
  const imp = useApi('/enps/driver-importance', { filters, params: { wave: 'Oct' } });
  const heat = useApi('/enps/heatmap', { filters, params: { row: 'thread', col: 'function', wave: hmWave } });
  const themes = useApi('/enps/themes', { filters });
  const exits = useApi('/enps/respondents-who-exited', { filters });
  const nrb = useApi('/enps/non-response-bias', { filters, params: { dim: 'thread' } });
  const nrbAll = useApi('/enps/non-response-bias', { filters });

  const k = kpis.data?.[0] || {};
  const pn = panel.data?.[0] || {};
  const oct = byWave.data?.find((r) => r.wave === 'Oct');
  const apr = byWave.data?.find((r) => r.wave === 'Apr');
  const nAll = nrbAll.data?.[0];
  const dimLabel = DIMS.find((d) => d[0] === dim)?.[1];

  const lowSegs = useMemo(() => (seg.data || []).filter((r) => r.low_response_oct || r.low_response_apr), [seg.data]);
  const lowNrb = useMemo(() => (nrb.data || []).filter((r) => r.low_response), [nrb.data]);

  // drill-down handlers (clicks add the clicked value to the global filters)
  const onSegClick = useCallback((e) => {
    const v = e.componentType === 'yAxis' ? e.value : e.data?.seg;
    if (v) drill({ [dim]: v });
  }, [drill, dim]);
  const onHeatClick = useCallback((e) => { const r = e.data?.r; if (r) drill({ thread: r.row_value, function: r.col_value }); }, [drill]);
  const onMixClick = useCallback((e) => {
    const label = e.componentType === 'yAxis' ? e.value : e.name;
    if (label) drill({ wave: label.startsWith('Apr') ? 'Apr' : 'Oct' });
  }, [drill]);
  const onNrbClick = useCallback((e) => { const v = e.componentType === 'xAxis' ? e.value : e.name; if (v) drill({ thread: v }); }, [drill]);

  const empty = (s) => !s.loading && !s.error && (!s.data || s.data.length === 0);
  const opt = { mobile };

  return (
    <div className="mx-auto max-w-[1400px] space-y-5 p-3 sm:p-5 lg:p-8">
      <PageHeader eyebrow="Employee sentiment" title="How do people feel about working at Porter?">
        Two pulse surveys, April and October 2026. eNPS asks how likely people are to recommend Porter as a place to work: % who would (9–10) minus % who would not (0–6). Click any bar, dot or cell to focus on that group.
      </PageHeader>

      <FilterBar />

      <KeyTakeaways endpoint="/enps/takeaways" />

      {/* KPI row */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Metric label="eNPS · Oct" icon={Activity} loading={kpis.loading && !kpis.data}
          value={fmtSigned(k.enps_oct)} suppressed={kpis.data && !isNum(k.enps_oct)} tone={k.enps_oct < 0 ? 'negative' : 'accent'}
          note={`n = ${fmtInt(k.n_oct)} respondents`} />
        <Metric label="eNPS · Apr" icon={Activity} loading={kpis.loading && !kpis.data}
          value={fmtSigned(k.enps_apr)} suppressed={kpis.data && !isNum(k.enps_apr)} tone={k.enps_apr < 0 ? 'negative' : undefined}
          note={`n = ${fmtInt(k.n_apr)} respondents`} />
        <Metric label="Change" icon={TrendingDown} loading={kpis.loading && !kpis.data}
          value={isNum(k.enps_change) ? `${fmtSigned(k.enps_change)} pts` : '–'} tone={k.enps_change < 0 ? 'negative' : 'accent'}
          note="October minus April"
          sub={isNum(pn.enps_change) ? `Same ${fmtInt(pn.n)} people: ${fmtSigned(pn.enps_change)} pts` : `Both-wave panel: n = ${fmtInt(pn.n)}`} />
        <Metric label="Response rate" icon={Users} loading={kpis.loading && !kpis.data}
          value={fmtPct(k.response_rate_oct_pct)}
          note={`Oct: ${fmtInt(k.n_oct)} of ${fmtInt(k.invited_oct)} invited`}
          sub={`April: ${fmtPct(k.response_rate_apr_pct)}`}
          badge={oct?.low_response ? <LowResponseBadge compact /> : null} />
        <Metric label="October mix" icon={MessageSquare} loading={kpis.loading && !kpis.data}>
          {kpis.data && isNum(k.pct_promoters_oct) ? (
            <div className="space-y-1.5">
              <div className="flex h-2.5 w-full overflow-hidden rounded-full">
                <div style={{ width: `${k.pct_detractors_oct}%`, background: p.negative }} />
                <div style={{ width: `${k.pct_passives_oct}%`, background: p.greyLight }} />
                <div style={{ width: `${k.pct_promoters_oct}%`, background: p.accent }} />
              </div>
              <div className="space-y-0.5 text-[11px] tabular-nums">
                <div className="flex justify-between"><span className="text-muted">Promoters</span><b className="text-accent">{fmtPct(k.pct_promoters_oct)}</b></div>
                <div className="flex justify-between"><span className="text-muted">Passives</span><b>{fmtPct(k.pct_passives_oct)}</b></div>
                <div className="flex justify-between"><span className="text-muted">Detractors</span><b className="text-negative">{fmtPct(k.pct_detractors_oct)}</b></div>
              </div>
            </div>
          ) : <div className="text-2xl font-bold text-muted">{kpis.data ? 'n<5' : '…'}</div>}
        </Metric>
        <Metric label="Respondents" icon={Users} loading={kpis.loading && !kpis.data}
          value={fmtInt(k.n)} note={`${fmtInt(k.n_apr)} April · ${fmtInt(k.n_oct)} October`}
          sub={apr?.low_response ? 'April response below 50%' : 'Valid responses, both waves'} />
      </section>

      {/* charts */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <Panel className="lg:col-span-7"
          title={`eNPS by ${dimLabel.toLowerCase()}: April vs October`}
          subtitle="Grey = April, blue = October; the line shows the change. Click a row to filter to it."
          n={seg.n} insightRows={seg.data} takeaway={seg.takeaway} sql={seg.sql} loading={seg.loading} error={seg.error} empty={empty(seg)}
          badges={lowSegs.length ? <LowResponseBadge detail={lowSegs.map((r) => `${r.segment} ${fmtPct(r.low_response_oct ? r.response_rate_oct_pct : r.response_rate_apr_pct, 0)}`).join(', ')} /> : null}
          actions={(
            <select value={dim} onChange={(e) => setDim(e.target.value)} aria-label="Break down by"
              className="h-6 rounded-md border border-border bg-surface px-1.5 text-[11px] font-medium outline-none">
              {DIMS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          )}>
          {(h) => seg.data && <EChart option={dumbbellOption(seg.data, p, opt)} height={h} onClick={onSegClick} />}
        </Panel>

        <Panel className="lg:col-span-5"
          title="Driver scores: % favourable, April vs October"
          subtitle="Share answering 4 or 5 on each 1–5 question; mean score and n in the tooltip."
          n={drivers.n} insightRows={drivers.data} takeaway={drivers.takeaway} sql={drivers.sql} loading={drivers.loading} error={drivers.error} empty={empty(drivers)}>
          {(h) => drivers.data && <EChart option={driversOption(drivers.data, p, opt)} height={h} />}
        </Panel>

        <Panel className="lg:col-span-7"
          title={`eNPS by thread × function (${hmWave === 'Oct' ? 'October' : 'April'} survey)`}
          subtitle="Red = negative, blue = positive eNPS; grey n<5 = fewer than 5 respondents; blank = no employees in that combination (corporate functions sit in Central). Click a cell to drill down."
          n={heat.n} insightRows={heat.data} takeaway={heat.takeaway} sql={heat.sql} loading={heat.loading} error={heat.error} empty={empty(heat)}
          actions={(
            <select value={hmWave} onChange={(e) => setHmWave(e.target.value)} aria-label="Survey wave" title="Survey wave"
              className="h-6 rounded-md border border-border bg-surface px-1.5 text-[11px] font-medium outline-none">
              <option value="Oct">October 2026 survey</option><option value="Apr">April 2026 survey</option>
            </select>
          )}>
          {(h) => heat.data && (
            <>
              {mobile && <div className="mb-1 text-[11px] text-muted">Swipe sideways to see every function →</div>}
              <EChart option={heatmapOption(heat.data, p, opt)} height={h} onClick={onHeatClick} minWidth={mobile ? 640 : undefined} />
            </>
          )}
        </Panel>

        <Panel className="lg:col-span-5"
          title="Which drivers matter most? Importance vs score (October survey)"
          subtitle="Right = more strongly linked to eNPS; low = lower score. Dashed lines = average of the five drivers."
          n={imp.n} insightRows={imp.data} takeaway={imp.takeaway} sql={imp.sql} loading={imp.loading} error={imp.error} empty={empty(imp) || (imp.data && imp.data.every((r) => r.suppressed))}>
          {(h) => imp.data && <EChart option={quadrantOption(imp.data, p)} height={h} />}
        </Panel>

        <Panel className="lg:col-span-4"
          title="Promoters, passives and detractors by wave"
          subtitle="Share of respondents per group; click a wave to filter."
          n={byWave.n} insightRows={byWave.data} takeaway={byWave.takeaway} sql={byWave.sql} loading={byWave.loading} error={byWave.error} empty={empty(byWave)}
          badges={(byWave.data || []).filter((r) => r.low_response).map((r) => <LowResponseBadge key={r.wave} detail={`${r.wave} ${fmtPct(r.response_rate_pct, 0)}`} />)}>
          {(h) => byWave.data && <EChart option={mixOption(byWave.data, p)} height={h} onClick={onMixClick} />}
        </Panel>

        <Panel className="lg:col-span-4"
          title="Comment themes: % of respondents, by wave"
          subtitle="Comments grouped into six themes."
          n={themes.n} insightRows={themes.data} takeaway={themes.takeaway} sql={themes.sql} loading={themes.loading} error={themes.error} empty={empty(themes)}>
          {(h) => themes.data && <EChart option={themesOption(themes.data, p)} height={h} />}
        </Panel>

        <Panel className="lg:col-span-4"
          title="April respondents who exited by 31-Oct, by April group"
          subtitle="Share of each April group who later left."
          n={exits.n} insightRows={exits.data} takeaway={exits.takeaway} nLabel="n Apr" sql={exits.sql} loading={exits.loading} error={exits.error} empty={empty(exits)}>
          {(h) => exits.data && <EChart option={exitsOption(exits.data, p)} height={h} />}
        </Panel>

        <Panel className="lg:col-span-12" height={280}
          title="Who skipped October? April eNPS of October respondents vs non-respondents, by thread"
          subtitle={nAll && isNum(nAll.apr_enps_oct_respondents)
            ? `People invited to both waves who answered in April. Overall, those who skipped October scored ${fmtSigned(nAll.apr_enps_oct_nonrespondents)} in April (n = ${fmtInt(nAll.n_oct_nonrespondents)}) vs ${fmtSigned(nAll.apr_enps_oct_respondents)} for those who answered again (n = ${fmtInt(nAll.n_oct_respondents)}). A lower grey bar means October eNPS is flattered by who chose to answer.`
            : 'People invited to both waves who answered in April.'}
          n={nrb.n} insightRows={nrb.data} takeaway={nrb.takeaway} nLabel="n eligible" sql={nrb.sql} loading={nrb.loading} error={nrb.error} empty={empty(nrb)}
          badges={lowNrb.length ? <LowResponseBadge detail={lowNrb.map((r) => `${r.segment} ${fmtPct(r.oct_response_rate_pct, 0)} answered Oct`).join(', ')} /> : null}>
          {(h) => nrb.data && <EChart option={nonResponseOption(nrb.data, p, opt)} height={h} onClick={onNrbClick} />}
        </Panel>
      </section>

      <PinnedAnswers dataset="enps" />
    </div>
  );
}
