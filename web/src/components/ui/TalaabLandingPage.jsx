import { useEffect, useRef, useState } from 'react';

const VIDEO_URL = 'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260908_125738_eb584080-9f98-489e-adb2-014760aa34da.mp4';
const POSTER_URL = 'https://images.higgs.ai/?default=1&output=webp&url=https%3A%2F%2Fd8j0ntlcm91z4.cloudfront.net%2Fuser_38xzZboKViGWJOttwIXH07lWA1P%2Fhf_20260908_122011_59c97465-4d23-4fdc-ac40-f6832f573e28.png&w=1920&q=85';

const NAV_ITEMS = [
  { label: 'Pond map', view: 'ponds' },
  { label: 'Plan', view: 'plan' },
  { label: 'Accuracy', view: 'accuracy' },
  { label: 'About', view: 'about' },
];

export default function TalaabLandingPage({ onExplore, onOpenView }) {
  const videoRef = useRef(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const openView = (view) => {
    setMenuOpen(false);
    if (view === 'ponds') onExplore?.();
    else onOpenView?.(view);
  };

  useEffect(() => {
    document.body.classList.toggle('menu-open', menuOpen);
    return () => document.body.classList.remove('menu-open');
  }, [menuOpen]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return undefined;
    let mounted = true;

    const reveal = () => {
      if (mounted) video.classList.add('is-ready');
    };
    const kick = () => {
      const playback = video.play();
      if (playback && typeof playback.catch === 'function') playback.catch(() => {});
    };
    if (video.readyState >= 3) reveal();
    else video.addEventListener('loadeddata', reveal, { once: true });
    kick();
    window.addEventListener('touchstart', kick, { once: true, passive: true });
    window.addEventListener('click', kick, { once: true });

    return () => {
      mounted = false;
      video.removeEventListener('loadeddata', reveal);
      window.removeEventListener('touchstart', kick);
      window.removeEventListener('click', kick);
    };
  }, []);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setMenuOpen(false);
    };
    const onResize = () => {
      if (window.innerWidth > 900) setMenuOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('resize', onResize);
    };
  }, [menuOpen]);

  const renderLinks = (className) => (
    <nav className={className} aria-label={className.includes('menu') ? 'Mobile navigation' : 'Primary navigation'}>
      {NAV_ITEMS.map((item) => (
        <button key={item.view} type="button" onClick={() => openView(item.view)}>{item.label}</button>
      ))}
    </nav>
  );

  return (
    <main
      className="talaab-hero"
      id="top"
      style={{ '--talaab-poster': `url("${POSTER_URL}")` }}
    >
      <div className="talaab-hero__media">
        <img
          className="talaab-hero__poster"
          src={POSTER_URL}
          alt="A vintage turntable resting on a mossy rock in an alpine meadow at golden hour"
          fetchPriority="high"
        />
        <video
          ref={videoRef}
          className="talaab-hero__video"
          autoPlay
          muted
          loop
          playsInline
          preload="auto"
          poster={POSTER_URL}
          aria-hidden="true"
          tabIndex={-1}
        >
          <source src={VIDEO_URL} type="video/mp4" />
        </video>
      </div>

      <header className="talaab-nav">
        <a className="talaab-wordmark" href="#top" aria-label="Talaab — home">
          Talaab<span className="talaab-wordmark-dot">.</span>
        </a>

        {renderLinks('talaab-nav-links')}

        <div className="talaab-nav-right">
          <button className="talaab-hero-cta talaab-nav-cta" type="button" onClick={onExplore}>
            Explore map <span aria-hidden="true">↗</span>
          </button>
          <button
            id="talaab-burger"
            className={`talaab-burger ${menuOpen ? 'is-active' : ''}`}
            type="button"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            aria-controls="talaab-menu"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span /><span /><span />
          </button>
        </div>
      </header>

      <div className="talaab-hero__inner">
        <h1 className="talaab-headline" id="talaab-hero-title">
          <span className="talaab-line"><span>Know your ponds.</span></span>
          <span className="talaab-line"><span>Before water runs low.</span></span>
        </h1>
      </div>

      <div
        className={`talaab-menu ${menuOpen ? 'is-open' : ''}`}
        id="talaab-menu"
        aria-hidden={!menuOpen}
      >
        <ul className="talaab-menu-list">
          {NAV_ITEMS.map((item, index) => (
            <li key={item.view} style={{ '--item-index': index }}>
              <button type="button" tabIndex={menuOpen ? 0 : -1} onClick={() => openView(item.view)}>{item.label}</button>
            </li>
          ))}
        </ul>
        <div className="talaab-menu-rule" />
        <div className="talaab-menu-foot">
          <button className="talaab-hero-cta" type="button" onClick={onExplore}>
            Explore the live map <span aria-hidden="true">↗</span>
          </button>
          <p>Water intelligence, with honest uncertainty.</p>
        </div>
      </div>
    </main>
  );
}
