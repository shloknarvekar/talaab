import { useEffect, useRef, useState } from 'react';
import ShinyButton from './ShinyButton';

// Local, web-optimized copy of the video supplied for the Talaab hero.
// Keep the asset in web/public/videos so Vite serves it directly without bundling it in JS.
const VIDEO_URL = '/videos/talaab-landing.mp4';
const POSTER_URL = '/videos/talaab-landing-poster.jpg';

const NAV_ITEMS = [
  { label: 'Pond map', view: 'ponds' },
  { label: 'Plan', view: 'plan' },
  { label: 'Accuracy', view: 'accuracy' },
  { label: 'About', view: 'about' },
];

export default function TalaabLandingPage({ onExplore, onOpenView }) {
  const videoRef = useRef(null);
  const proofRef = useRef(null);

  // The clip carries a small mark near its bottom-right corner (1160, 600 in the 1280x720 frame). The video is
  // cropped to fill the screen (object-fit: cover, object-position 50% 62%), so the mark moves with the window
  // shape: place the proof card over it. Phones crop the sides away (mark off-screen) and keep the CSS position.
  useEffect(() => {
    const place = () => {
      const card = proofRef.current;
      const hero = card?.closest('.talaab-hero');
      if (!card || !hero) return;
      card.style.left = ''; card.style.top = ''; card.style.right = ''; card.style.bottom = '';
      if (window.innerWidth <= 760) return;
      const box = hero.getBoundingClientRect();
      const scale = Math.max(box.width / 1280, box.height / 720);
      const x = (box.width - 1280 * scale) / 2 + 1160 * scale;
      const y = (box.height - 720 * scale) * 0.62 + 600 * scale;
      if (x < 0 || x > box.width || y < 0 || y > box.height) return;
      const w = card.offsetWidth; const h = card.offsetHeight;
      const parent = (card.offsetParent || hero).getBoundingClientRect();  // left/top are relative to this box
      const left = Math.max(16, Math.min(x - w * 0.8, box.width - w - 12));
      const top = Math.max(16, Math.min(y - h / 2, box.height - h - 12));
      card.style.left = `${left + box.left - parent.left}px`;
      card.style.top = `${top + box.top - parent.top}px`;
      card.style.right = 'auto'; card.style.bottom = 'auto';
    };
    place();
    window.addEventListener('resize', place);
    return () => window.removeEventListener('resize', place);
  }, []);
  const [menuOpen, setMenuOpen] = useState(false);
  const prefersPoster = () => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true || navigator.connection?.saveData === true;
  };
  const [posterOnly, setPosterOnly] = useState(prefersPoster);

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
    const motionQuery = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    const connection = navigator.connection;
    const updatePosterMode = () => setPosterOnly(motionQuery?.matches === true || connection?.saveData === true);
    motionQuery?.addEventListener?.('change', updatePosterMode);
    connection?.addEventListener?.('change', updatePosterMode);
    updatePosterMode();
    return () => {
      motionQuery?.removeEventListener?.('change', updatePosterMode);
      connection?.removeEventListener?.('change', updatePosterMode);
    };
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (posterOnly || !video) return undefined;
    let mounted = true;
    const reveal = () => { if (mounted) video.classList.add('is-ready'); };
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
      video.pause();
      video.removeEventListener('loadeddata', reveal);
      window.removeEventListener('touchstart', kick);
      window.removeEventListener('click', kick);
    };
  }, [posterOnly]);

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
          alt="A satellite above the Earth, the opening frame of the Talaab landing video"
          fetchPriority="high"
        />
        {!posterOnly && <video
          ref={videoRef}
          className="talaab-hero__video"
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
          poster={POSTER_URL}
          aria-hidden="true"
          tabIndex={-1}
        >
          <source src={VIDEO_URL} type="video/mp4" />
        </video>}
      </div>

      <header className="talaab-nav">
        <a className="talaab-wordmark" href="#top" aria-label="Talaab — home">
          Talaab<span className="talaab-wordmark-dot" aria-hidden="true" />
        </a>

        {renderLinks('talaab-nav-links')}

        <div className="talaab-nav-right">
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
        <div className="talaab-hero-actions">
          <ShinyButton onClick={onExplore}>Explore the live map <span aria-hidden="true">→</span></ShinyButton>
        </div>
        <figure className="talaab-proof" ref={proofRef}>
          <div className="talaab-proof-frames">
            <span><img src="/imagery/latur-2024/P003/2024-01-16.jpg" alt="Pond P003 full of water, 16 January 2024" width="88" height="88" /><small>16 Jan</small></span>
            <span aria-hidden="true" className="talaab-proof-arrow">→</span>
            <span><img src="/imagery/latur-2024/P003/2024-05-30.jpg" alt="The same pond nearly dry, 30 May 2024" width="88" height="88" /><small>30 May</small></span>
          </div>
          <figcaption><b>The same pond in Latur, 2024.</b> Real Sentinel-2 passes, four and a half months apart: the sun and the season took most of it.</figcaption>
        </figure>
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
