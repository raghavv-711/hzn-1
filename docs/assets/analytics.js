// Visitor counts with GoatCounter (free, no cookies, no personal data).
// To turn it on, put your GoatCounter site code here, e.g. 'hzn-1' for https://hzn-1.goatcounter.com.
// Leave it empty and nothing is loaded.
const GOATCOUNTER = '';

if (GOATCOUNTER && location.hostname.endsWith('github.io')) {
  const s = document.createElement('script');
  s.async = true;
  s.src = 'https://gc.zgo.at/count.js';
  s.dataset.goatcounter = 'https://' + GOATCOUNTER + '.goatcounter.com/count';
  document.head.appendChild(s);
}
