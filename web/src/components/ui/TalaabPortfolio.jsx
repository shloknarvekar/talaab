import HoverRevealCards from './HoverRevealCards';
const stories = [
  {
    number: '01',
    eyebrow: 'OBSERVE',
    title: 'Every pond. One living picture.',
    description: 'Scan pond locations and risk across a whole region before deciding where to send a field team.',
    image: '/imagery/latur-2024/P003/2024-01-16.jpg',
    frame: '2024-01-16',
    tone: 'moss',
    wide: true,
  },
  {
    number: '02',
    eyebrow: 'MEASURE',
    title: 'See what water is doing.',
    description: 'Compare water-area readings across usable satellite passes, with suspect observations kept visible as suspect.',
    image: '/imagery/latur-2024/P003/2024-03-06.jpg',
    frame: '2024-03-06',
    tone: 'clay',
    wide: false,
  },
  {
    number: '03',
    eyebrow: 'FORECAST',
    title: 'Plan around a window, not a guess.',
    description: 'Use a drying range to understand urgency—without pretending a forecast can name the exact day.',
    image: '/imagery/latur-2024/P003/2024-04-15.jpg',
    frame: '2024-04-15',
    tone: 'blue',
    wide: false,
  },
  {
    number: '04',
    eyebrow: 'TAKE ACTION',
    title: 'Move from signal to field action.',
    description: 'Turn evidence into inspection priorities and a district plan, while keeping the reason for each flag clear.',
    image: '/imagery/latur-2024/P003/2024-05-30.jpg',
    frame: '2024-05-30',
    tone: 'violet',
    wide: true,
  },
];

export default function TalaabPortfolio({ onExplore }) {
  const interactiveStories = stories.map((story) => ({
    id: story.number,
    title: story.title,
    subtitle: `${story.eyebrow} · ${story.frame}`,
    imageUrl: story.image,
    imageClassName: 'portfolio-card-frame',
    description: story.description,
    detail: `${story.description} This card uses a locally stored Sentinel-2 frame of pond P003 near Latur dated ${story.frame}.`,
    actionLabel: 'Explore story',
  }));

  return (
    <section className="talaab-portfolio" aria-labelledby="portfolio-title">
      <header className="portfolio-heading">
        <div className="portfolio-heading-copy">
          <h2 id="portfolio-title">The sun drinks first.<br /><em>Talaab says when.</em></h2>
          <p>
            Talaab measures every pond in a drought district from free Sentinel-2 passes, gives each one a dry-by range, and flags ponds shrinking faster than the sun can explain, so officers know where to send tankers and inspectors first.
          </p>
        </div>
        <button className="portfolio-cta" type="button" onClick={onExplore}>
          Explore the pond map <span aria-hidden="true">↗</span>
        </button>
      </header>

      <HoverRevealCards
        items={interactiveStories}
        heading="Follow the workflow"
        eyebrow="FROM SATELLITE TO FIELD"
        density="regular"
        className="portfolio-hover-cards"
        ariaLabel="Interactive Talaab workflow stories"
      />
      <p className="portfolio-footnote">Forecasts are decision support, not guarantees. “Faster than the sun” is an inspection signal—not proof of pumping.</p>
    </section>
  );
}
