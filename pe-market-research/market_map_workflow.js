export const meta = {
  name: 'pe-market-research',
  description: 'PE-style market map: discover players, verify capital structure, assess M&A fit, output facts-only tables',
  phases: [
    { title: 'Discover', detail: 'find players by region/category until rounds stop yielding new names' },
    { title: 'Profile', detail: 'per-player: founding, ownership, revenue, capital ties, product/raw-material facts' },
    { title: 'Assess', detail: 'score M&A/OEM fit from confirmed facts only' },
    { title: 'Verify', detail: 'adversarial re-check of contested or contradictory claims' },
  ],
}

// args = {
//   industry: string,              // e.g. "糖アルコール(sugar alcohol) manufacturers"
//   knownPlayers: string[],         // players already confirmed — seeds discovery, avoids re-finding them
//   regions: string[],              // regions/countries to sweep for discovery, e.g. ["Turkey","Nigeria","Russia",...]
//   assessAxis: string,             // what "fit" means for this engagement, e.g. "independent OEM candidate with no capital ties to competitor X"
// }

const P = typeof args === 'string' ? JSON.parse(args) : (args || {})
log(`args typeof=${typeof args}, industry=${P.industry}, regions=${JSON.stringify(P.regions)}`)

const industry = P.industry
const known = P.knownPlayers || []
const regions = P.regions || []
const assessAxis = P.assessAxis || 'general M&A / OEM fit'

// ---- Stage 1: Discover — sweep regions in parallel, loop each region until 2 dry rounds ----
// A region is "dry" when a fresh search yields no name outside `seen`.
phase('Discover')

const seen = new Set(known.map(n => n.toLowerCase()))
const discovered = []

const DISCOVERY_SCHEMA = {
  type: 'object',
  properties: {
    companies: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          country: { type: 'string' },
          products: { type: 'string' },
          raw_material: { type: 'string' },
          confidence: { type: 'string', enum: ['一次', '一次寄り', '要検証'] },
          source_url: { type: 'string' },
        },
        required: ['name', 'country', 'products', 'confidence'],
      },
    },
  },
  required: ['companies'],
}

async function discoverRegion(region) {
  let dry = 0
  const localFound = []
  while (dry < 2) {
    const result = await agent(
      `Find companies that manufacture ${industry} in/from ${region}. ` +
      `Already known (do NOT re-report these): ${[...seen].join(', ') || '(none yet)'}. ` +
      `For each NEW company found, verify via its official website (WebFetch) — do not report a company on search-snippet text alone. ` +
      `Distinguish manufacturers from importers/distributors/traders — a company that sells but does not make the product does not count. ` +
      `Report only what you can source: company name, country, product(s), raw material if stated, confidence tag ([一次] official site direct / [一次寄り] secondary but consistent / [要検証] search-only), source URL. ` +
      `If you find nothing new, say so explicitly — do not pad the report with already-known companies.`,
      { phase: 'Discover', label: `discover:${region}`, schema: DISCOVERY_SCHEMA }
    )
    const fresh = (result.companies || []).filter(c => !seen.has(c.name.toLowerCase()))
    if (!fresh.length) { dry++; continue }
    dry = 0
    fresh.forEach(c => seen.add(c.name.toLowerCase()))
    localFound.push(...fresh)
  }
  return { region, companies: localFound }
}

const regionResults = await parallel(regions.map(r => () => discoverRegion(r)))
regionResults.filter(Boolean).forEach(r => discovered.push(...r.companies))

log(`Discovery done: ${discovered.length} new players across ${regions.length} regions (started from ${known.length} known)`)

// ---- Stage 2+3: Profile then Assess, pipelined per player (no barrier — fast players don't wait on slow ones) ----
const PROFILE_SCHEMA = {
  type: 'object',
  properties: {
    founded: { type: 'string' },
    hq: { type: 'string' },
    listed: { type: 'string', description: 'exchange+ticker, or "non-listed", or "unknown"' },
    ownership: { type: 'string', description: 'controlling shareholder / family / state / PE / strategic — with % if found' },
    revenue: { type: 'string' },
    capital_ties: { type: 'string', description: 'JVs, past M&A (acquired/was acquired), foreign stakes' },
    core_business_share: { type: 'string', description: 'what fraction of the company this product line actually represents' },
    export_profile: { type: 'string' },
    confidence: { type: 'string', enum: ['一次', '一次寄り', '要検証'] },
    sources: { type: 'array', items: { type: 'string' } },
  },
  required: ['listed', 'ownership', 'confidence'],
}

const ASSESS_SCHEMA = {
  type: 'object',
  properties: {
    fit_verdict: { type: 'string', enum: ['strong_fit', 'partial_fit', 'poor_fit', 'insufficient_data'] },
    reasoning: { type: 'string', description: 'grounded ONLY in facts from the profile stage — no speculation' },
  },
  required: ['fit_verdict', 'reasoning'],
}

const pipelineResults = await pipeline(
  discovered,
  company => agent(
    `Research the capital structure of ${company.name} (${company.country}), a ${industry} manufacturer, using only primary sources (official site, stock exchange filings, national business registries) with secondary press as fallback. ` +
    `Cover: listed/non-listed + ticker, ownership/shareholder structure (family/state/PE/strategic, with % if disclosed), latest annual revenue, any capital tie-ups (JVs, M&A history as acquirer or target, foreign stakes), what fraction of the company's total business this product line represents, export vs. domestic sales profile. ` +
    `Tag every claim [一次]/[一次寄り]/[要検証] and cite the source URL. State only what you verified — write "未確認" for anything you could not source, never fill gaps with plausible-sounding guesses.`,
    { phase: 'Profile', label: `profile:${company.name}`, schema: PROFILE_SCHEMA }
  ),
  (profile, company) => profile ? agent(
    `Given this verified profile of ${company.name}: ${JSON.stringify(profile)}. ` +
    `Assess fit against this axis: "${assessAxis}". ` +
    `Base the verdict ONLY on facts present in the profile — if a needed fact is "未確認", the verdict must reflect that gap (do not assume the best case). ` +
    `Do not narrate what you initially thought or what changed — state the current verdict and the facts supporting it only.`,
    { phase: 'Assess', label: `assess:${company.name}`, schema: ASSESS_SCHEMA }
  ).then(assess => ({ profile, assess })) : null
)

const assessed = discovered
  .map((c, i) => ({ company: c, profile: pipelineResults[i]?.profile, assess: pipelineResults[i]?.assess }))
  .filter(x => x.profile)

// ---- Stage 4: Verify — adversarial re-check for any profile with contradictions or [要検証] on a load-bearing field ----
phase('Verify')

const needsVerify = assessed.filter(x =>
  x.profile.confidence === '要検証' || x.assess?.fit_verdict === 'insufficient_data'
)

const verified = await parallel(needsVerify.map(x => () => agent(
  `Independently re-verify this claim about ${x.company.name}: ${JSON.stringify(x.profile)}. ` +
  `Try to either confirm with a primary source you haven't checked yet, or refute it. Default to "still 要検証" if genuinely unresolvable — do not upgrade confidence without a new source.`,
  { phase: 'Verify', label: `verify:${x.company.name}`, schema: { type: 'object', properties: { resolution: { type: 'string' }, new_confidence: { type: 'string', enum: ['一次', '一次寄り', '要検証'] }, source: { type: 'string' } }, required: ['resolution', 'new_confidence'] } }
).then(v => ({ name: x.company.name, verification: v }))))

// ---- Output: facts-only, no process narrative ----
// Per feedback_result_not_process.md: write current facts + confidence tag + source. Never "originally X, corrected to Y".
return {
  discovered_count: discovered.length,
  players: assessed.map(x => ({
    name: x.company.name,
    country: x.company.country,
    products: x.company.products,
    raw_material: x.company.raw_material,
    profile: x.profile,
    assess: x.assess,
  })),
  verification_followups: verified.filter(Boolean),
}
