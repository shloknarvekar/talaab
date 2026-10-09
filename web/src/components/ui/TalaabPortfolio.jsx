const stories = [
  {
    number: '01',
    eyebrow: 'OBSERVE',
    title: 'Every pond. One living picture.',
    description: 'Scan pond locations and risk across a whole region before deciding where to send a field team.',
    image: 'https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=1500&q=85',
    tone: 'moss',
    wide: true,
  },
  {
    number: '02',
    eyebrow: 'MEASURE',
    title: 'See what water is doing.',
    description: 'Compare water-area readings across usable satellite passes, with suspect observations kept visible as suspect.',
    image: 'https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=1200&q=85',
    tone: 'clay',
    wide: false,
  },
  {
    number: '03',
    eyebrow: 'FORECAST',
    title: 'Plan around a window, not a guess.',
    description: 'Use a drying range to understand urgency—without pretending a forecast can name the exact day.',
    image: 'https://images.unsplash.com/photo-1501785888041-af3ef285b470?auto=format&fit=crop&w=1200&q=85',
    tone: 'blue',
    wide: false,
  },
  {
    number: '04',
    eyebrow: 'TAKE ACTION',
    title: 'Move from signal to field action.',
    description: 'Turn evidence into inspection priorities and a district plan, while keeping the reason for each flag clear.',
    image: 'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1500&q=85',
    tone: 'violet',
    wide: true,
  },
];

export default function TalaabPortfolio({ onExplore }) {
  return (
    <section className="talaab-portfolio" aria-labelledby="portfolio-title">
      <header className="portfolio-heading">
        <div className="portfolio-heading-copy">
          <span className="eyebrow">FIELD INTELLIGENCE · WATER RESILIENCE</span>
          <h2 id="portfolio-title">Better signals.<br /><em>Earlier action.</em></h2>
          <p>
            Talaab turns satellite observations into a clearer picture of pond health—so field teams can focus attention where water may run short first.
          </p>
        </div>
        <button className="portfolio-cta" type="button" onClick={onExplore}>
          Explore the pond map <span aria-hidden="true">↗</span>
        </button>
      </header>

      <div className="portfolio-grid">
        {stories.map((story) => (
          <article className={`portfolio-card portfolio-card-${story.tone} ${story.wide ? 'portfolio-card-wide' : ''}`} key={story.number}>
            <img
              className="portfolio-card-image"
              src={story.image}
              alt=""
              loading="lazy"
              onError={(event) => { event.currentTarget.style.visibility = 'hidden'; }}
            />
            <div className="portfolio-card-shade" aria-hidden="true" />
            <div className="portfolio-card-content">
              <span className="portfolio-card-kicker"><b>{story.number}</b> / {story.eyebrow}</span>
              <h3>{story.title}</h3>
              <p>{story.description}</p>
            </div>
            <span className="portfolio-card-mark" aria-hidden="true">T.</span>
          </article>
        ))}
      </div>
      <p className="portfolio-footnote">Forecasts are decision support, not guarantees. “Faster than the sun” is an inspection signal—not proof of pumping.</p>
    </section>
  );
}
