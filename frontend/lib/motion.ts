'use client';
import {useEffect, useState, RefObject} from 'react';

/**
 * Motion preference. "quiet" is set either by the operating system
 * (prefers-reduced-motion) or by the in-app Quiet motion switch, which adds
 * data-motion="quiet" to <html>. Both are read after mount so the static
 * export and the first client render agree.
 */
export function prefersQuietMotion(): boolean {
  if (typeof window === 'undefined') return true;
  if (document.documentElement.dataset.motion === 'quiet') return true;
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

export function useQuietMotion(): boolean {
  const [quiet, setQuiet] = useState(true);
  useEffect(() => {
    const update = () => setQuiet(prefersQuietMotion());
    update();
    const media = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    media?.addEventListener?.('change', update);
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {attributes: true, attributeFilter: ['data-motion']});
    return () => {
      media?.removeEventListener?.('change', update);
      observer.disconnect();
    };
  }, []);
  return quiet;
}

/** Reports whether an element is (partly) inside the viewport. */
export function useInView(ref: RefObject<Element | null>, rootMargin = '120px'): boolean {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return;
    }
    const observer = new IntersectionObserver(entries => setInView(entries.some(e => e.isIntersecting)), {rootMargin});
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, rootMargin]);
  return inView;
}
