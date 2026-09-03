// Maritime Edge AI Intelligence Platform — landing site interactions
// Progressive enhancement: without JS the page is fully readable and navigable.

(function () {
    'use strict';

    var navToggle = document.getElementById('navToggle');
    var navLinks = document.getElementById('navLinks');
    var navbar = document.getElementById('navbar');
    var progress = document.querySelector('.scroll-progress');
    var backToTop = document.querySelector('.back-to-top');
    var reduceMotion = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Mark that JS is active (CSS gates reveal/hover-motion on this class)
    document.documentElement.classList.add('js');

    // ---------- Mobile nav toggle (with aria sync) ----------
    if (navToggle && navLinks) {
        navToggle.addEventListener('click', function () {
            var open = navLinks.classList.toggle('active');
            navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
    }

    // ---------- Smooth scroll for in-page nav links ----------
    document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
        anchor.addEventListener('click', function (e) {
            var target = document.querySelector(anchor.getAttribute('href'));
            if (!target) { return; }
            e.preventDefault();
            target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
            if (navLinks) { navLinks.classList.remove('active'); }
            if (navToggle) { navToggle.setAttribute('aria-expanded', 'false'); }
        });
    });

    // ---------- Scroll: navbar state, reading progress, back-to-top ----------
    var ticking = false;
    function onScroll() {
        if (ticking) { return; }
        ticking = true;
        window.requestAnimationFrame(function () {
            var y = window.scrollY || document.documentElement.scrollTop;
            navbar.classList.toggle('scrolled', y > 50);

            if (backToTop) {
                backToTop.classList.toggle('show', y > 600);
            }
            if (progress) {
                var doc = document.documentElement;
                var max = doc.scrollHeight - window.innerHeight;
                progress.style.transform = 'scaleX(' + (max > 0 ? Math.min(y / max, 1) : 0) + ')';
            }
            ticking = false;
        });
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    if (backToTop) {
        backToTop.addEventListener('click', function () {
            window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
        });
    }

    // ---------- Scroll-reveal (IntersectionObserver only) ----------
    if ('IntersectionObserver' in window) {
        var revealSelectors = [
            '.section-header', '.content-grid', '.image-wide',
            '.conclusion-content', '.download-card'
        ];
        var staggerSelectors = [
            '.constraints-grid', '.services-grid', '.testing-grid', '.dashboard-modes'
        ];

        revealSelectors.forEach(function (sel) {
            document.querySelectorAll(sel).forEach(function (el) { el.classList.add('reveal'); });
        });
        staggerSelectors.forEach(function (sel) {
            document.querySelectorAll(sel).forEach(function (el) {
                el.classList.add('reveal', 'reveal-stagger');
            });
        });

        var revealObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                    revealObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });

        document.querySelectorAll('.reveal').forEach(function (el) {
            revealObserver.observe(el);
        });

        // ---------- Hero stat count-up ----------
        if (!reduceMotion) {
            var stats = document.querySelectorAll('.hero .stat-number');
            if (stats.length) {
                var statObserver = new IntersectionObserver(function (entries) {
                    entries.forEach(function (entry) {
                        if (!entry.isIntersecting) { return; }
                        animateCount(entry.target);
                        statObserver.unobserve(entry.target);
                    });
                }, { threshold: 0.5 });
                stats.forEach(function (el) { statObserver.observe(el); });
            }
        }
    }

    function animateCount(el) {
        var original = el.textContent.trim();
        var match = original.match(/^(\d+)(.*)$/);
        if (!match) { return; }
        var end = parseInt(match[1], 10);
        var suffix = match[2];
        var duration = 900;
        var start = null;

        function frame(ts) {
            if (start === null) { start = ts; }
            var p = Math.min((ts - start) / duration, 1);
            var eased = 1 - Math.pow(1 - p, 3); // ease-out cubic
            el.textContent = Math.round(eased * end) + suffix;
            if (p < 1) {
                window.requestAnimationFrame(frame);
            } else {
                el.textContent = original; // restore exact original string
            }
        }
        window.requestAnimationFrame(frame);
    }

    // ---------- Lightbox: click any content image to view it larger ----------
    var lightboxLinks = Array.prototype.slice.call(
        document.querySelectorAll('.lightbox-link')
    );

    if (lightboxLinks.length) {
        var lightbox = null;
        var lbImg = null;
        var lbCaption = null;
        var lbCounter = null;
        var lbPrev = null;
        var lbNext = null;
        var lbClose = null;
        var currentIndex = 0;
        var lastFocused = null;

        function captionFor(link) {
            var fig = link.closest('figure');
            if (fig) {
                var cap = fig.querySelector('.placeholder-label');
                if (cap && cap.textContent.trim()) { return cap.textContent.trim(); }
            }
            var img = link.querySelector('img');
            return img && img.alt ? img.alt : link.getAttribute('aria-label') || '';
        }

        function ensureLightbox() {
            if (lightbox) { return; }
            lightbox = document.createElement('div');
            lightbox.className = 'lightbox';
            lightbox.setAttribute('role', 'dialog');
            lightbox.setAttribute('aria-modal', 'true');
            lightbox.setAttribute('aria-label', 'Image viewer');

            lbClose = document.createElement('button');
            lbClose.type = 'button';
            lbClose.className = 'lightbox-close';
            lbClose.setAttribute('aria-label', 'Close image viewer');
            lbClose.innerHTML = '&times;';

            lbPrev = document.createElement('button');
            lbPrev.type = 'button';
            lbPrev.className = 'lightbox-nav prev';
            lbPrev.setAttribute('aria-label', 'Previous image');
            lbPrev.innerHTML = '&lsaquo;';

            lbNext = document.createElement('button');
            lbNext.type = 'button';
            lbNext.className = 'lightbox-nav next';
            lbNext.setAttribute('aria-label', 'Next image');
            lbNext.innerHTML = '&rsaquo;';

            var figure = document.createElement('figure');
            figure.className = 'lightbox-figure';
            lbImg = document.createElement('img');
            lbImg.alt = '';
            figure.appendChild(lbImg);

            lbCaption = document.createElement('figcaption');
            lbCaption.className = 'lightbox-caption';
            figure.appendChild(lbCaption);

            lbCounter = document.createElement('div');
            lbCounter.className = 'lightbox-counter';

            lightbox.appendChild(lbClose);
            lightbox.appendChild(lbPrev);
            lightbox.appendChild(lbNext);
            lightbox.appendChild(figure);
            lightbox.appendChild(lbCounter);
            document.body.appendChild(lightbox);

            lbClose.addEventListener('click', closeLightbox);
            lbPrev.addEventListener('click', function () { showImage(currentIndex - 1); });
            lbNext.addEventListener('click', function () { showImage(currentIndex + 1); });
            lightbox.addEventListener('click', function (e) {
                if (e.target === lightbox) { closeLightbox(); }
            });
        }

        function showImage(index) {
            currentIndex = Math.max(0, Math.min(index, lightboxLinks.length - 1));
            var link = lightboxLinks[currentIndex];
            var img = link.querySelector('img');
            lbImg.src = link.getAttribute('href');
            lbImg.alt = img ? img.alt : '';
            lbCaption.textContent = captionFor(link);
            lbCounter.textContent = (currentIndex + 1) + ' / ' + lightboxLinks.length;
            lbPrev.disabled = currentIndex === 0;
            lbNext.disabled = currentIndex === lightboxLinks.length - 1;
        }

        function openLightbox(link, index) {
            ensureLightbox();
            lastFocused = link;
            showImage(index);
            lightbox.classList.add('open');
            document.body.classList.add('lightbox-open');
            lbClose.focus();
        }

        function closeLightbox() {
            if (!lightbox) { return; }
            lightbox.classList.remove('open');
            document.body.classList.remove('lightbox-open');
            if (lastFocused) { lastFocused.focus(); }
        }

        lightboxLinks.forEach(function (link, index) {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                openLightbox(link, index);
            });
        });

        document.addEventListener('keydown', function (e) {
            if (!lightbox || !lightbox.classList.contains('open')) { return; }
            if (e.key === 'Escape') {
                closeLightbox();
            } else if (e.key === 'ArrowLeft') {
                showImage(currentIndex - 1);
            } else if (e.key === 'ArrowRight') {
                showImage(currentIndex + 1);
            }
        });
    }

    // ---------- Scrollspy: highlight current section in nav ----------
    if ('IntersectionObserver' in window) {
        var spyLinks = document.querySelectorAll('.nav-links a[href^="#"]');
        if (spyLinks.length) {
            var spyObserver = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (!entry.isIntersecting) { return; }
                    var id = entry.target.id;
                    spyLinks.forEach(function (link) {
                        link.classList.toggle('active', link.getAttribute('href') === '#' + id);
                    });
                });
            }, { rootMargin: '-40% 0px -55% 0px', threshold: 0 });
            ['challenge', 'sar', 'edge-ai', 'architecture', 'detection', 'dashboard', 'testing', 'conclusion']
                .forEach(function (id) {
                    var section = document.getElementById(id);
                    if (section) { spyObserver.observe(section); }
                });
        }
    }
})();
