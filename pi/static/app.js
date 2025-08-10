// ---------- FIRE ENGINE ----------
const fireWidth  = 90;   // logical pixels (canvas width)
const fireHeight = 40;   // logical pixels (canvas height)
const HARD_GRIP  = 150;  // lbs at which flames hit max intensity
const BASE_FIRE_INTENSITY = 5;   // keep a tiny flame always

const firePixels = new Array(fireWidth * fireHeight).fill(0);
const palette = [
  "#070707","#1f0707","#2f0f07","#470f07","#571707","#671f07","#771f07",
  "#8f2707","#9f2f07","#af3f07","#bf4707","#c74707","#df4f07","#df5707","#df5707","#d75f07",
  "#d7670f","#cf6f0f","#cf770f","#cf7f0f","#cf8717","#c78717","#c78f17","#c7971f","#bf9f1f",
  "#bf9f1f","#bfa727","#bfa727","#bfa727","#c7af2f","#c7af2f","#c7b72f","#c7b737","#cfbf37",
  "#cfbf37","#cfbf37","#d7c747","#d7c747","#d7cf4f","#d7cf4f","#dfd75f","#dfd75f","#dfdf6f",
  "#efef9f","#ffffff"
];

const canvas = document.getElementById("fireCanvas");
const ctx    = canvas.getContext("2d");
canvas.width  = fireWidth;
canvas.height = fireHeight;

function index(x,y){ return y*fireWidth + x; }

function setFireSource(intensity){
  for(let x=0;x<fireWidth;x++) firePixels[index(x,fireHeight-1)] = intensity;
}

function updateFire(){
  for (let y = 0; y < fireHeight - 1; y++){
    for (let x = 0; x < fireWidth; x++){
      const src   = index(x, y);
      const below = src + fireWidth;
      const decay = Math.floor(Math.random() * 3);
      const newInt = Math.max(firePixels[below] - decay, 0);
      const dst   = src - decay + 1;
      firePixels[(dst < firePixels.length) ? dst : src] = newInt;
    }
  }
}

function renderFire(){
  const img = ctx.getImageData(0,0,fireWidth,fireHeight);
  for(let i=0;i<firePixels.length;i++){
    const color = palette[firePixels[i]];
    const r=parseInt(color.substr(1,2),16), g=parseInt(color.substr(3,2),16), b=parseInt(color.substr(5,2),16);
    img.data[i*4+0]=r; img.data[i*4+1]=g; img.data[i*4+2]=b; img.data[i*4+3]=255;
  }
  ctx.putImageData(img,0,0);
}

function fireLoop(){ updateFire(); renderFire(); requestAnimationFrame(fireLoop); }

// show a little flame at idle
setFireSource(BASE_FIRE_INTENSITY);
fireLoop();

// ---------- POLLING & INTENSITY MAPPING ----------
let grip=0, max=0;
async function poll(){
  try{
    const r = await fetch("/data");
    if(r.ok){
      const j = await r.json();
      grip=j.grip; max=j.max;
      document.getElementById("grip").textContent = grip.toFixed(2)+" lbs";
      document.getElementById("max").textContent  =  max.toFixed(2)+" lbs";
      const pctRaw = grip / HARD_GRIP;
      const pct = Math.max(0, Math.min(pctRaw, 1));
      let intensity = Math.round(pct * (palette.length - 1));
      if (!(intensity >= 0)) intensity = BASE_FIRE_INTENSITY; // fallback if NaN
      intensity = Math.max(BASE_FIRE_INTENSITY, Math.min(intensity, palette.length - 1));
      setFireSource(intensity);
    }
  }catch(e){ /* ignore transient errors */ }
  setTimeout(poll,200);
}
poll();

// ---------- TOASTS (green, auto-dismiss) ----------
function showToast(msg, type){
  const t=document.createElement('div');
  t.className='toast'+(type==='error'?' error':'');
  t.textContent=msg;
  document.body.appendChild(t);
  requestAnimationFrame(()=>t.classList.add('show'));
  setTimeout(()=>{t.classList.remove('show');t.addEventListener('transitionend',()=>t.remove(),{once:true});},1800);
}

// ---------- META & BUTTONS ----------
const nameInput  = document.getElementById("nameInput");
const sideSelect = document.getElementById("sideSelect");
const hUser      = document.getElementById("user");

function sendMeta(){
  const name = nameInput.value.trim() || "guest";
  const side = sideSelect.value;
  hUser.textContent = `${name} (${side.charAt(0).toUpperCase()+side.slice(1)})`;
  fetch("/meta",{ method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ name, side }) });
}
nameInput.addEventListener("input",  sendMeta);
sideSelect.addEventListener("change", sendMeta);

const saveBtn  = document.getElementById("saveBtn");
const maxLabel = document.getElementById("max");
saveBtn.addEventListener("click", (e) =>{
  e.preventDefault();
  fetch("/savemax",{
    method : "POST",
    headers: {"Content-Type":"application/json"},
    body   : JSON.stringify({
      value : parseFloat(maxLabel.textContent),   // e.g. 137.2
      name  : document.getElementById("nameInput").value.trim() || "guest",
      side  : document.getElementById("sideSelect").value
    })
  }).then(r => { r.ok ? showToast("Saved!") : showToast("Save failed","error"); })
    .catch(()=> showToast("Save failed","error"));
});

document.getElementById("resetBtn").addEventListener("click", () =>{
  fetch("/reset", {method:"POST"}).then(()=>{
    document.getElementById("grip").textContent = "0.00 lbs";
    document.getElementById("max").textContent  = "0.00 lbs";
    showToast("Cleared");
  });
});

(function(){
  const section = document.getElementById('dashboardSection');
  const btn = document.getElementById('toggleDashboard');
  if(!section || !btn) return;
  const KEY = 'dashboardHidden';
  // initialize from saved state
  const hidden = localStorage.getItem(KEY) === '1';
  if(hidden){
    section.classList.add('dashboard-hidden');
    btn.setAttribute('aria-pressed','true');
    btn.setAttribute('aria-expanded','false');
    btn.title = 'Show dashboard';
    btn.textContent = 'Show Dashboard';
  } else {
    btn.setAttribute('aria-pressed','false');
    btn.setAttribute('aria-expanded','true');
    btn.title = 'Hide dashboard';
    btn.textContent = 'Hide Dashboard';
  }
  btn.addEventListener('click', ()=>{
    const isHidden = section.classList.toggle('dashboard-hidden');
    localStorage.setItem(KEY, isHidden ? '1' : '0');
    btn.setAttribute('aria-pressed', isHidden ? 'true' : 'false');
    btn.setAttribute('aria-expanded', isHidden ? 'false' : 'true');
    btn.title = isHidden ? 'Show dashboard' : 'Hide dashboard';
    btn.textContent = isHidden ? 'Show Dashboard' : 'Hide Dashboard';
  });
})();