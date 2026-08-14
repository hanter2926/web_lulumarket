(function(){
  'use strict';

  function Carousel(root){
    this.root = root;
    this.container = root.querySelector('.carousel');
    this.slides = Array.from(root.querySelectorAll('.carousel-slide'));
    this.prev = root.querySelector('.carousel-prev');
    this.next = root.querySelector('.carousel-next');
    this.dots = root.querySelector('.carousel-dots');
    this.current = 0;
    this.timer = null;
    this.autoplay = true;
    if(root.dataset && root.dataset.autoplay === 'false') this.autoplay = false;

    this.init();
  }

  Carousel.prototype.init = function(){
    if(this.slides.length <= 1){
      if(this.prev) this.prev.style.display = 'none';
      if(this.next) this.next.style.display = 'none';
      if(this.dots) this.dots.style.display = 'none';
    }

    this.slides.forEach((s, i) => {
      s.style.transition = 'opacity 0.6s ease';
      s.style.position = 'absolute';
      s.style.top = 0;
      s.style.left = 0;
      s.style.width = '100%';
      s.style.opacity = i===0 ? '1' : '0';
      s.style.zIndex = i===0 ? '2' : '1';
    });

    this.buildDots();
    this.bind();
    if(this.autoplay) this.startTimer();
  };

  Carousel.prototype.buildDots = function(){
    if(!this.dots) return;
    this.dots.innerHTML = '';
    this.slides.forEach((s, i) => {
      const btn = document.createElement('button');
      btn.className = 'carousel-dot' + (i===0 ? ' active' : '');
      btn.dataset.index = i;
      btn.addEventListener('click', (e) => { this.goTo(i); });
      this.dots.appendChild(btn);
    });
  };

  Carousel.prototype.bind = function(){
    if(this.prev) this.prev.addEventListener('click', () => this.prevSlide());
    if(this.next) this.next.addEventListener('click', () => this.nextSlide());
    this.root.addEventListener('mouseenter', () => this.pause());
    this.root.addEventListener('mouseleave', () => this.resume());
  };

  Carousel.prototype.prevSlide = function(){
    const idx = (this.current - 1 + this.slides.length) % this.slides.length;
    this.goTo(idx);
  };

  Carousel.prototype.nextSlide = function(){
    const idx = (this.current + 1) % this.slides.length;
    this.goTo(idx);
  };

  Carousel.prototype.goTo = function(idx){
    if(idx === this.current) return;
    const old = this.current;
    this.slides[old].style.opacity = '0';
    this.slides[old].style.zIndex = '1';
    this.slides[idx].style.opacity = '1';
    this.slides[idx].style.zIndex = '2';
    this.current = idx;
    this.updateDots();
    this.restartTimer();
  };

  Carousel.prototype.updateDots = function(){
    if(!this.dots) return;
    const buttons = Array.from(this.dots.children);
    buttons.forEach((b, i) => b.classList.toggle('active', i===this.current));
  };

  Carousel.prototype.startTimer = function(){
    if(this.timer) clearTimeout(this.timer);
    const slide = this.slides[this.current];
    const interval = parseInt(slide.dataset.interval || '5', 10) * 1000;
    this.timer = setTimeout(() => this.nextSlide(), interval);
  };

  Carousel.prototype.restartTimer = function(){
    if(!this.autoplay) return;
    this.startTimer();
  };

  Carousel.prototype.pause = function(){
    if(this.timer) clearTimeout(this.timer);
  };

  Carousel.prototype.resume = function(){
    if(this.autoplay) this.startTimer();
  };

  document.addEventListener('DOMContentLoaded', function(){
    const roots = document.querySelectorAll('#site-carousel');
    roots.forEach(r => new Carousel(r));
  });
})();
