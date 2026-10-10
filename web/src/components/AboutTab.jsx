import TalaabPortfolio from './ui/TalaabPortfolio';
const REPO = 'https://github.com/shloknarvekar/talaab';

export default function AboutTab({ onExplore }) {
  return <section className="about-screen about-screen--atlas">
    <TalaabPortfolio onExplore={onExplore} />

    <section className="about-section architecture-section" id="about-architecture">
      <div className="architecture-intro">
        
        <h3>From satellite pass<br /><em>to district action.</em></h3>
        <p>The forecast remains deterministic. Satellite readings are cleaned, snapshots are published by date, and the action plan can only use the numbers Talaab has already produced.</p>
        <div className="architecture-note"><span>01</span><p>One evidence trail, from a clear-sky observation to a field-ready priority.</p></div>
      </div>
      <div className="architecture-system">
        <div className="architecture-flow" aria-label="Talaab data pipeline">
          <article className="architecture-stage stage-schedule"><div className="architecture-stage-top"><span>STEP 01</span><b>↻</b></div><h4>Schedule & measure</h4><p>Every 5 days, EventBridge Scheduler starts Step Functions and splits the district into 42 grid cells. Each cell is measured on its own Lambda using Sentinel-2 straight from AWS Open Data—about a minute for 7,157 km².</p><div className="architecture-stage-tags"><span>EventBridge</span><span>Step Functions</span><span>Lambda</span></div></article>
          <div className="architecture-connector" aria-hidden="true"><span>→</span></div>
          <article className="architecture-stage stage-publish"><div className="architecture-stage-top"><span>STEP 02</span><b>▤</b></div><h4>Clean & publish</h4><p>The merge step cleans readings; recompute builds a snapshot per date in Amazon S3 and DynamoDB so each view stays honest about what was known.</p><div className="architecture-stage-tags"><span>Amazon S3</span><span>DynamoDB</span></div></article>
          <div className="architecture-connector" aria-hidden="true"><span>→</span></div>
          <article className="architecture-stage stage-notify"><div className="architecture-stage-top"><span>STEP 03</span><b>↗</b></div><h4>Prioritize & notify</h4><p>Amazon SNS emails the district officer about ponds that newly need action. Forecasting stays deterministic; the plan writer on Amazon Bedrock may only use these numbers.</p><div className="architecture-stage-tags"><span>Amazon SNS</span><span>Open model / Lambda</span></div></article>
        </div>
        <div className="architecture-platform"><span className="eyebrow">SUPPORTING PLATFORM</span><div className="aws-chip-row"><span>AWS Open Data</span><span>API Gateway</span><span>Amazon Bedrock</span><span>CloudWatch</span><span>Amplify Hosting</span></div></div>
      </div>
    </section>

    <section className="about-section credits-section credits-section--atlas" id="about-sources">
      <header className="credits-heading"><div><h3>Open data.<br /><em>Clear provenance.</em></h3><p>Every view should make it possible to understand where its evidence came from and what its limits are.</p></div><a className="github-link" href={REPO} target="_blank" rel="noreferrer">View source on GitHub ↗</a></header>
      <div className="credits-grid">
        <article className="credit-source credit-source-earth" id="source-satellite"><span className="credit-source-index">Earth observation</span><div className="credit-source-symbol" aria-hidden="true"><svg className="inline-icon earth-icon" viewBox="0 0 16 16" focusable="false"><circle cx="8" cy="8" r="6"/><path d="M2.5 6h11M3.5 10h9M8 2c1.4 1.6 2.1 3.6 2.1 6S9.4 12.4 8 14M8 2C6.6 3.6 5.9 5.6 5.9 8S6.6 12.4 8 14"/></svg></div><h4>Copernicus Sentinel-2</h4><p>Sentinel-2 L2A imagery via AWS Open Data / Element84 Earth Search.</p><small>Source credit · Copernicus</small></article>
        <article className="credit-source credit-source-weather" id="source-weather"><span className="credit-source-index">Weather inputs</span><div className="credit-source-symbol" aria-hidden="true">☼</div><h4>Open-Meteo</h4><p>Daily reference evapotranspiration (ET₀) and precipitation used by the backend.</p><small>Licence · CC BY 4.0</small></article>
        <article className="credit-source credit-source-maps" id="source-maps"><span className="credit-source-index">Geography</span><div className="credit-source-symbol" aria-hidden="true">⌖</div><h4>OpenStreetMap + CARTO</h4><p>Geographic context and basemap tiles for exploring ponds and districts.</p><small>© OpenStreetMap contributors (ODbL) · © CARTO</small></article>
      </div>
      <div className="credits-footnote"><p>Historical views are labelled <b>2024 replay</b>; live views use the latest published region snapshot. Drying dates are presented as ranges, not guarantees. “Faster than the sun” suggests pumping and should prompt inspection, not an accusation.</p></div>
    </section>

    <footer className="about-footer about-footer--atlas"><span>Syntax Errors · Environmental Hacks · Heat & Water</span><span>Designed for district officers, field teams and a water-secure future.</span></footer>
  </section>;
}
