import { useCallback } from 'react';
import { Briefcase, CheckCircle2, Clock, FolderOpen, Handshake, IndianRupee, Info, Timer, UserCheck, Users } from 'lucide-react';
import FilterBar from '../components/FilterBar';
import PageHeader from '../components/PageHeader';
import KeyTakeaways from '../components/KeyTakeaways';
import PinnedAnswers from '../components/PinnedAnswers';
import Metric from '../components/Metric';
import Panel from '../components/Panel';
import EChart from '../components/EChart';
import DataTable from '../components/DataTable';
import { useFilters } from '../context/FilterContext';
import { useTheme } from '../context/ThemeContext';
import { useApi } from '../lib/api';
import { useIsMobile } from '../lib/useMedia';
import { fmtINRLakh, fmtInt, fmtPct, isNum } from '../lib/format';
import {
  agingOption, funnelOption, interviewersOption, monthLabel, monthlyOption, offersOption, stageTimeOption, ttfGradeOption,
} from './hiringCharts';

const days = (v) => (isNum(v) ? `${Number.isInteger(v) ? v : v.toFixed(1)} d` : '–');
const inr = (v) => (isNum(v) && v > 0 ? `₹${Math.round(v).toLocaleString('en-IN')}` : '–');

export default function Hiring() {
  const { filters, drill } = useFilters();
  const { palette: p } = useTheme();
  const mobile = useIsMobile();
  const opt = { mobile };

  const kpis = useApi('/hiring/kpis', { filters });
  const monthly = useApi('/hiring/monthly', { filters });
  const funnel = useApi('/hiring/funnel', { filters });
  const stage = useApi('/hiring/stage-time', { filters });
  const grade = useApi('/hiring/ttf-by-grade', { filters });
  const source = useApi('/hiring/source', { filters });
  const fair = useApi('/hiring/recruiter-comparison', { filters });
  const attain = useApi('/hiring/recruiters', { filters });
  const iv = useApi('/hiring/interviewers', { filters });
  const offers = useApi('/hiring/offers', { filters });
  const offSum = useApi('/hiring/offers-summary', { filters });
  const aging = useApi('/hiring/open-aging-buckets', { filters });
  const slaPairs = useApi('/hiring/sla-mismatch', { filters });
  const slaList = useApi('/hiring/sla-mismatch-list', { filters });

  const k = kpis.data?.[0] || {};
  const loadingK = kpis.loading && !kpis.data;
  const empty = (s) => !s.loading && !s.error && (!s.data || s.data.length === 0);

  // drill-down handlers
  const onMonth = useCallback((e) => {
    const rows = monthly.data || [];
    const row = e.componentType === 'xAxis' ? rows.find((r) => monthLabel(r.month) === e.value) : rows[e.dataIndex];
    if (row) drill({ raised_month_from: row.month, raised_month_to: row.month });
  }, [drill, monthly.data]);
  const onGrade = useCallback((e) => { const g = e.componentType === 'xAxis' ? e.value : e.name; if (g) drill({ grade: g }); }, [drill]);

  // merge fair comparison + attainment (both from the API) for the recruiter table
  const recruiterRows = (fair.data || []).map((r) => ({ ...r, ...(attain.data || []).find((a) => a.recruiter === r.recruiter) }));
  const offerTxt = (() => {
    const a = offSum.data?.find((r) => r.outcome === 'Accepted');
    const d = offSum.data?.find((r) => r.outcome === 'Declined');
    if (!a || !d) return null;
    return `Median offered ÷ expected CTC: accepted ${a.median_offer_to_expected.toFixed(2)} (n = ${fmtInt(a.n)}) vs declined ${d.median_offer_to_expected.toFixed(2)} (n = ${fmtInt(d.n)}). `
      + `Median offered ÷ budget max: ${a.median_offer_to_budget.toFixed(2)} vs ${d.median_offer_to_budget.toFixed(2)}. Offers sit well under budget.`;
  })();

  return (
    <div className="mx-auto max-w-[1400px] space-y-5 p-3 sm:p-5 lg:p-8">
      <PageHeader eyebrow="Hiring" title="How fast and how well is Porter hiring?">
        Job openings raised 01-Apr to 15-Oct-2026, status as of 31-Oct-2026. Time to fill counts from the day an opening is raised to the day the hire accepts. Click bars, rows or grades to focus on them.
      </PageHeader>

      <FilterBar />

      <KeyTakeaways endpoint="/hiring/takeaways" />

      <section className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <Metric label="Reqs raised" icon={Briefcase} loading={loadingK} value={fmtInt(k.reqs_raised)}
          note={`${fmtInt(k.on_hold_or_archived)} on hold or archived`} />
        <Metric label="Open reqs" icon={FolderOpen} loading={loadingK} value={fmtInt(k.open_reqs)}
          note={`${fmtInt(k.open_past_sla)} already past SLA`} />
        <Metric label="Filled" icon={CheckCircle2} loading={loadingK} value={fmtInt(k.filled_reqs)}
          note={`${fmtInt(k.filled_joined)} joined · ${fmtInt(k.filled_yet_to_join)} yet to join`} />
        <Metric label="Median time to fill" icon={Timer} loading={loadingK} value={days(k.median_ttf_days)}
          note={`n = ${fmtInt(k.filled_reqs)} filled reqs`} sub="Raised → offer accepted" />
        <Metric label="Filled within SLA" icon={Clock} loading={loadingK} value={fmtPct(k.pct_within_sla)}
          note={`of ${fmtInt(k.filled_reqs)} filled (recomputed)`} />
        <Metric label="Offer acceptance" icon={Handshake} loading={loadingK} value={fmtPct(k.offer_acceptance_pct)}
          note={`${fmtInt(k.offers_accepted)} accepted of ${fmtInt((k.offers_accepted ?? 0) + (k.offers_declined ?? 0))}`} />
        <Metric label="Joining rate" icon={UserCheck} loading={loadingK} value={fmtPct(k.joining_rate_pct)}
          note={`${fmtInt(k.joined_of_due)} joined of ${fmtInt(k.joining_due)} due by 31-Oct`} />
        <Metric label="Agency fees" icon={IndianRupee} loading={loadingK} value={fmtINRLakh(k.agency_fees_lakh)}
          note={`${fmtInt(k.agency_joiners)} agency joiners × 8.33% of CTC`} />
        <Metric label="Open past SLA" icon={Clock} loading={loadingK} value={fmtInt(k.open_past_sla)}
          tone={k.open_past_sla > 0 ? 'negative' : undefined} note={`of ${fmtInt(k.open_reqs)} open reqs`} />
        <Metric label="Applicants" icon={Users} loading={loadingK} value={fmtInt(k.applicants)}
          note="Candidate applications on these reqs" />
      </section>

      {filters.source && (
        <div className="flex items-start gap-2 rounded-lg border border-accent/30 bg-accent-soft px-3 py-2 text-xs text-primary">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
          <span>Openings = openings with at least one applicant from this source; Filled and TTF = openings filled by a hire from this source.</span>
        </div>
      )}

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <Panel className="lg:col-span-7" title="Reqs raised vs offers accepted vs joins, by month"
          subtitle="Reqs by month raised; offers by month accepted; joins by month joined. Click a month to filter to reqs raised then."
          n={monthly.n} insightRows={monthly.data} takeaway={monthly.takeaway} nLabel="n reqs" sql={monthly.sql} loading={monthly.loading} error={monthly.error} empty={empty(monthly)}>
          {(h) => monthly.data && <EChart option={monthlyOption(monthly.data, p)} height={h} onClick={onMonth} />}
        </Panel>

        <Panel className="lg:col-span-5" title="Candidate funnel by stage"
          subtitle="Label = candidates · % of the previous stage (log scale so late stages stay visible)."
          n={funnel.n} insightRows={funnel.data} takeaway={funnel.takeaway} nLabel="n candidates" sql={funnel.sql} loading={funnel.loading} error={funnel.error} empty={empty(funnel)}>
          {(h) => funnel.data && <EChart option={funnelOption(funnel.data, p, opt)} height={h} />}
        </Panel>

        <Panel className="lg:col-span-7" title="Median time to fill by grade vs SLA"
          subtitle="Bars = median days from req raised to offer accepted (red = above SLA); dashed line = SLA; label = % filled within SLA. Click a grade to drill down."
          n={grade.n} insightRows={grade.data} takeaway={grade.takeaway} nLabel="n reqs" sql={grade.sql} loading={grade.loading} error={grade.error} empty={empty(grade) || (grade.data && grade.data.every((r) => !r.filled))}>
          {(h) => grade.data && <EChart option={ttfGradeOption(grade.data, p)} height={h} onClick={onGrade} />}
        </Panel>

        <Panel className="lg:col-span-5" title="Where the days go: median days per stage"
          subtitle="Between consecutive stage dates (valid order only). Response → join is mostly the notice period."
          n={stage.n} insightRows={stage.data} takeaway={stage.takeaway} nLabel="n candidates" sql={stage.sql} loading={stage.loading} error={stage.error} empty={empty(stage)}>
          {(h) => stage.data && <EChart option={stageTimeOption(stage.data, p)} height={h} />}
        </Panel>

        <Panel className="lg:col-span-12" title="Source effectiveness: volume, conversion, speed and cost by source" height={0}
          subtitle="Hire = candidate who filled a req (joined or yet to join). Agency cost per joiner = 8.33% fees ÷ agency joiners. Click a row to filter."
          n={source.n} insightRows={source.data} takeaway={source.takeaway} nLabel="n candidates" sql={source.sql} loading={source.loading} error={source.error} empty={empty(source)}>
          {() => source.data && (
            <DataTable rows={source.data} rowKey={(r) => r.source} onRowClick={(r) => drill({ source: r.source })}
              defaultSort={{ key: 'applicants', dir: 'desc' }}
              columns={[
                { key: 'source', label: 'Source' },
                { key: 'applicants', label: 'Applicants', align: 'right', format: fmtInt },
                { key: 'hires', label: 'Hires', align: 'right', format: fmtInt },
                { key: 'applicant_to_hire_pct', label: 'Applicant → hire', align: 'right', format: (v) => fmtPct(v, 2), bar: { max: Math.max(...source.data.map((r) => r.applicant_to_hire_pct || 0)), color: p.accent } },
                { key: 'median_ttf_days', label: 'Median TTF', align: 'right', format: days, title: 'Median TTF of reqs filled from this source' },
                { key: 'offer_acceptance_pct', label: 'Offer acceptance', align: 'right', format: (v) => fmtPct(v) },
                { key: 'cost_per_joiner_inr', label: 'Agency cost / joiner', align: 'right', format: inr },
              ]} />
          )}
        </Panel>

        <Panel className="lg:col-span-12" title="Recruiters: fair comparison per assigned req, plus attainment vs target" height={0}
          subtitle="Compare recruiters on the per-req columns (filled %, median TTF, % within SLA, accepted offers per req). Attainment = accepted offers per month (Apr–Oct, 7 months) ÷ monthly target, shown counting all accepted offers and excluding backed-out candidates. Click a row to filter."
          n={fair.n} insightRows={fair.data} takeaway={fair.takeaway} nLabel="n reqs" sql={fair.sql} loading={fair.loading || attain.loading} error={fair.error || attain.error} empty={empty(fair)}
          footer={<p className="mt-2 text-[11px] leading-4 text-muted"><b>Note:</b> attainment depends on how many reqs a recruiter is given; a recruiter with few reqs cannot reach a fixed monthly offer target, so low attainment can mean low load rather than low performance.</p>}>
          {() => fair.data && (
            <DataTable rows={recruiterRows} dense rowKey={(r) => r.recruiter} onRowClick={(r) => drill({ recruiter: r.recruiter })}
              defaultSort={{ key: 'reqs_assigned', dir: 'desc' }}
              columns={[
                { key: 'recruiter', label: 'Recruiter' },
                { key: 'reqs_assigned', label: 'Reqs assigned (share)', headWidth: 110, align: 'right', format: (v, r) => `${fmtInt(v)}${isNum(r.pct_of_reqs) ? ` (${r.pct_of_reqs}%)` : ''}`, bar: { max: Math.max(...recruiterRows.map((r) => r.reqs_assigned || 0)), color: p.grey } },
                { key: 'filled_pct', label: 'Filled %', headWidth: 64, align: 'right', format: (v) => fmtPct(v) },
                { key: 'median_ttf_days', label: 'Median TTF', headWidth: 64, align: 'right', format: days },
                { key: 'pct_filled_within_sla', label: 'Filled within SLA', headWidth: 72, align: 'right', format: (v) => fmtPct(v) },
                { key: 'open_past_sla', label: 'Open past SLA', headWidth: 64, align: 'right', format: fmtInt },
                { key: 'accepted_per_assigned_req', label: 'Accepted offers per req', headWidth: 84, align: 'right', format: (v) => (isNum(v) ? v.toFixed(2) : '–') },
                { key: 'monthly_offer_target', label: 'Target per month', headWidth: 64, align: 'right', format: fmtInt },
                { key: 'attainment_all_pct', label: 'Attainment (all accepted)', headWidth: 96, align: 'right', format: (v) => fmtPct(v), bar: { max: 100, color: p.accent } },
                { key: 'attainment_excl_bo_pct', label: 'Attainment (excl. backed out)', headWidth: 96, align: 'right', format: (v) => fmtPct(v) },
              ]} />
          )}
        </Panel>

        <Panel className="lg:col-span-7" title="15 slowest R1 interviewers: median days to submit feedback" height={340}
          subtitle="Interviewers with at least 5 interviews with feedback; red = median over 2 days. Names from People_Directory (hiring data only)."
          n={iv.n} insightRows={iv.data} takeaway={iv.takeaway} nLabel="n interviews" sql={iv.sql} loading={iv.loading} error={iv.error} empty={empty(iv)}>
          {(h) => iv.data && <EChart option={interviewersOption(iv.data, p, opt)} height={h} />}
        </Panel>

        <Panel className="lg:col-span-5" title="Offer declines by offered ÷ expected CTC" height={300}
          subtitle="Share of offers declined in each band of offered CTC relative to what the candidate expected."
          n={offers.n} insightRows={offers.data} takeaway={offers.takeaway} nLabel="n offers" sql={offers.sql} loading={offers.loading} error={offers.error} empty={empty(offers)}
          footer={offerTxt && <p className="mt-2 text-[11px] leading-4 text-muted">{offerTxt}</p>}>
          {(h) => offers.data && <EChart option={offersOption(offers.data, p)} height={h} />}
        </Panel>

        <Panel className="lg:col-span-5" title="Open reqs on 31-Oct: how far past SLA" height={300}
          subtitle="Age of each open req (31-Oct − raised) compared with its SLA days."
          n={aging.n} insightRows={aging.data} takeaway={aging.takeaway} nLabel="n open reqs" sql={aging.sql} loading={aging.loading} error={aging.error} empty={empty(aging)}>
          {(h) => aging.data && <EChart option={agingOption(aging.data, p)} height={h} />}
        </Panel>

        <Panel className="lg:col-span-7" title="SLA status: ATS system vs recomputed" height={300}
          subtitle="The recomputed status (TTF ≤ SLA days; open reqs breached when age > SLA) is used everywhere. Highlighted rows disagree with the ATS."
          n={slaPairs.n} nLabel="n reqs" takeaway={slaPairs.takeaway} sql={slaPairs.sql} loading={slaPairs.loading || slaList.loading} error={slaPairs.error || slaList.error} empty={empty(slaPairs)}>
          {() => slaPairs.data && (
            <div className="space-y-3">
              <DataTable rows={slaPairs.data} dense highlight={(r) => r.mismatch} rowKey={(r) => `${r.system_status}-${r.recomputed_status}`}
                defaultSort={{ key: 'reqs', dir: 'desc' }}
                columns={[
                  { key: 'system_status', label: 'ATS status' },
                  { key: 'recomputed_status', label: 'Recomputed' },
                  { key: 'reqs', label: 'Reqs', align: 'right', format: fmtInt },
                  { key: 'mismatch', label: 'Mismatch', format: (v) => (v ? <span className="font-semibold text-warn">Yes</span> : 'No') },
                ]} />
              <DataTable rows={slaList.data || []} dense maxHeight={190} rowKey={(r) => r.req_id}
                defaultSort={{ key: 'days_over_sla', dir: 'desc' }}
                columns={[
                  { key: 'req_id', label: 'Req' },
                  { key: 'grade', label: 'Grade' },
                  { key: 'recruiter', label: 'Recruiter' },
                  { key: 'ttf_days', label: 'TTF', align: 'right', format: days },
                  { key: 'sla_days', label: 'SLA', align: 'right', format: days },
                  { key: 'days_over_sla', label: 'Over SLA', align: 'right', format: (v) => <span className="font-semibold text-negative">{days(v)}</span> },
                  { key: 'had_backout', label: 'Backout', format: (v) => (v ? 'Yes' : '') },
                ]} />
            </div>
          )}
        </Panel>
      </section>

      <PinnedAnswers dataset="hiring" />
    </div>
  );
}
