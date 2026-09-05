/**
 * PIHU Orb — WebGL Shader Engine
 * VoicePoweredOrb GLSL with dramatically boosted visibility.
 */

import { Renderer, Program, Mesh, Triangle, Vec3 } from "ogl";

// ─── Types ────────────────────────────────────────────────────────────────────

export type OrbState =
  | "IDLE"
  | "WAKE_DETECTED"
  | "LISTENING"
  | "TRANSCRIBING"
  | "THINKING"
  | "PLANNING"
  | "EXECUTING"
  | "RESPONDING"
  | "ERROR";

interface StateParams {
  hue: number;
  baseRotSpeed: number;
  voiceMultiplier: number;
  hoverIntensity: number;
  hoverBase: number;
  opacity: number;
  noiseFreq: number;
  brightness: number;   // multiplier on final shader color (1.0 = reference)
}

const STATE_PARAMS: Record<OrbState, StateParams> = {
  IDLE: {
    hue: 0, baseRotSpeed: 0.08, voiceMultiplier: 0,
    hoverIntensity: 0, hoverBase: 0,
    opacity: 0, noiseFreq: 0.3, brightness: 2.5,
  },
  WAKE_DETECTED: {
    hue: 30, baseRotSpeed: 1.8, voiceMultiplier: 0,
    hoverIntensity: 0.7, hoverBase: 1.0,
    opacity: 1, noiseFreq: 2.5, brightness: 4.0,
  },
  LISTENING: {
    hue: 0, baseRotSpeed: 0.4, voiceMultiplier: 1.8,
    hoverIntensity: 0.9, hoverBase: 0.15,
    opacity: 1, noiseFreq: 1.0, brightness: 3.5,
  },
  TRANSCRIBING: {
    hue: 195, baseRotSpeed: 0.7, voiceMultiplier: 0.4,
    hoverIntensity: 0.4, hoverBase: 0.5,
    opacity: 1, noiseFreq: 1.4, brightness: 3.2,
  },
  THINKING: {
    hue: 260, baseRotSpeed: 1.0, voiceMultiplier: 0,
    hoverIntensity: 0.25, hoverBase: 0.25,
    opacity: 1, noiseFreq: 0.8, brightness: 3.0,
  },
  PLANNING: {
    hue: 45, baseRotSpeed: 0.55, voiceMultiplier: 0,
    hoverIntensity: 0.2, hoverBase: 0.2,
    opacity: 1, noiseFreq: 0.6, brightness: 3.0,
  },
  EXECUTING: {
    hue: 185, baseRotSpeed: 2.0, voiceMultiplier: 0,
    hoverIntensity: 0.5, hoverBase: 0.55,
    opacity: 1, noiseFreq: 2.0, brightness: 3.5,
  },
  RESPONDING: {
    hue: 15, baseRotSpeed: 0.45, voiceMultiplier: 1.4,
    hoverIntensity: 0.8, hoverBase: 0.35,
    opacity: 1, noiseFreq: 1.1, brightness: 3.5,
  },
  ERROR: {
    hue: -120, baseRotSpeed: 0.3, voiceMultiplier: 0,
    hoverIntensity: 0.35, hoverBase: 0.65,
    opacity: 1, noiseFreq: 0.5, brightness: 3.0,
  },
};

// ─── GLSL ─────────────────────────────────────────────────────────────────────

const VERT = /* glsl */`
  precision highp float;
  attribute vec2 position;
  attribute vec2 uv;
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position, 0.0, 1.0);
  }
`;

const FRAG = /* glsl */`
  precision highp float;

  uniform float iTime;
  uniform vec3  iResolution;
  uniform float hue;
  uniform float hover;
  uniform float rot;
  uniform float hoverIntensity;
  uniform float brightness;   /* NEW — brightness multiplier */

  varying vec2 vUv;

  /* ── Colour helpers ──────────────────────────────────────────── */
  vec3 rgb2yiq(vec3 c){
    return vec3(dot(c,vec3(0.299,0.587,0.114)),
                dot(c,vec3(0.596,-0.274,-0.322)),
                dot(c,vec3(0.211,-0.523,0.312)));
  }
  vec3 yiq2rgb(vec3 c){
    return vec3(c.x+0.956*c.y+0.621*c.z,
                c.x-0.272*c.y-0.647*c.z,
                c.x-1.106*c.y+1.703*c.z);
  }
  vec3 adjustHue(vec3 col,float deg){
    float r=deg*3.14159265/180.0;
    vec3 y=rgb2yiq(col);
    float ca=cos(r),sa=sin(r);
    y.yz=vec2(y.y*ca-y.z*sa, y.y*sa+y.z*ca);
    return yiq2rgb(y);
  }

  /* ── Noise ───────────────────────────────────────────────────── */
  vec3 hash33(vec3 p){
    p=fract(p*vec3(0.1031,0.11369,0.13787));
    p+=dot(p,p.yxz+19.19);
    return -1.0+2.0*fract(vec3(p.x+p.y,p.x+p.z,p.y+p.z)*p.zyx);
  }
  float snoise3(vec3 p){
    const float K1=0.333333333,K2=0.166666667;
    vec3 i=floor(p+(p.x+p.y+p.z)*K1);
    vec3 d0=p-(i-(i.x+i.y+i.z)*K2);
    vec3 e=step(vec3(0.0),d0-d0.yzx);
    vec3 i1=e*(1.0-e.zxy),i2=1.0-e.zxy*(1.0-e);
    vec3 d1=d0-(i1-K2),d2=d0-(i2-K1),d3=d0-0.5;
    vec4 h=max(0.6-vec4(dot(d0,d0),dot(d1,d1),dot(d2,d2),dot(d3,d3)),0.0);
    vec4 n=h*h*h*h*vec4(dot(d0,hash33(i)),dot(d1,hash33(i+i1)),
                        dot(d2,hash33(i+i2)),dot(d3,hash33(i+1.0)));
    return dot(vec4(31.316),n);
  }

  /* ── Base palette — vivid, pre-boosted ──────────────────────── */
  const vec3 C1 = vec3(0.72, 0.28, 1.00);   /* vivid purple   */
  const vec3 C2 = vec3(0.20, 0.75, 1.00);   /* electric cyan  */
  const vec3 C3 = vec3(0.05, 0.05, 0.55);   /* deep indigo    */
  const float innerRadius = 0.55;
  const float noiseScale  = 0.65;

  float L1(float I,float A,float d){return I/(1.0+d*A);}
  float L2(float I,float A,float d){return I/(1.0+d*d*A);}

  vec4 draw(vec2 uv){
    vec3 c1=adjustHue(C1,hue);
    vec3 c2=adjustHue(C2,hue);
    vec3 c3=adjustHue(C3,hue);

    float ang=atan(uv.y,uv.x);
    float len=length(uv);
    float invLen=len>0.0?1.0/len:0.0;

    float n0=snoise3(vec3(uv*noiseScale,iTime*0.5))*0.5+0.5;
    float r0=mix(mix(innerRadius,1.0,0.4),mix(innerRadius,1.0,0.6),n0);
    float d0=distance(uv,(r0*invLen)*uv);
    float v0=L1(1.0,8.0,d0);
    v0*=smoothstep(r0*1.05,r0,len);
    float cl=cos(ang+iTime*2.0)*0.5+0.5;

    float a=iTime*-1.0;
    vec2 pos=vec2(cos(a),sin(a))*r0;
    float d1=distance(uv,pos);
    float v1=L2(2.0,4.0,d1)*L1(1.0,40.0,d0);

    float v2=smoothstep(1.0,mix(innerRadius,1.0,n0*0.5),len);
    float v3=smoothstep(innerRadius,mix(innerRadius,1.0,0.5),len);

    vec3 col=mix(c1,c2,cl);
    col=mix(c3,col,v0);
    col=(col+v1)*v2*v3;
    col=clamp(col,0.0,1.0);

    /* ── Boost: scale colour by brightness uniform ────────────── */
    col *= brightness;

    /* ── Opaque sphere body (dark glass base) ────────────────── */
    /* Any pixel inside the unit circle gets a minimum dark fill  */
    float inside = smoothstep(1.02, 0.98, len);   /* 1 inside, 0 outside */
    float bodyAlpha = inside * 0.82;               /* semi-opaque glass   */
    vec3  bodyColor = inside * mix(vec3(0.04,0.02,0.12), col, 0.6);

    /* Final composite: glass body + bright nebula on top */
    vec3  finalRGB = bodyColor + col * (1.0 - bodyAlpha);
    float finalA   = max(bodyAlpha, clamp(dot(col, vec3(0.333)), 0.0, 1.0));

    return vec4(finalRGB, finalA);
  }

  void main(){
    vec2 center=iResolution.xy*0.5;
    float sz=min(iResolution.x,iResolution.y);
    vec2 uv=(vUv*iResolution.xy-center)/sz*2.0;

    float s=sin(rot),c2=cos(rot);
    uv=vec2(c2*uv.x-s*uv.y, s*uv.x+c2*uv.y);

    uv.x+=hover*hoverIntensity*0.1*sin(uv.y*10.0+iTime);
    uv.y+=hover*hoverIntensity*0.1*sin(uv.x*10.0+iTime);

    vec4 col=draw(uv);
    gl_FragColor=vec4(col.rgb*col.a, col.a);
  }
`;

// ─── PihuOrb ─────────────────────────────────────────────────────────────────

export class PihuOrb {
  private container: HTMLElement;
  private renderer: Renderer;
  private gl: WebGLRenderingContext | WebGL2RenderingContext;
  private program: Program;

  private currentState: OrbState = "IDLE";
  private targetState:  OrbState = "IDLE";
  private transitionProgress = 1.0;

  private currentHue            = 0;
  private currentHover          = 0;
  private currentHoverIntensity = 0;
  private currentRot            = 0;
  private currentBrightness     = 2.5;
  private currentOpacity        = 0;

  private audioLevel       = 0;
  private targetAudioLevel = 0;
  private wakeFlash        = 0;
  private rafId            = 0;
  private lastTime         = 0;

  constructor(canvas: HTMLCanvasElement) {
    this.container = canvas.parentElement as HTMLElement;

    this.renderer = new Renderer({
      canvas,
      alpha: true,
      premultipliedAlpha: true,   // premult gives better glass blending
      antialias: true,
      dpr: window.devicePixelRatio || 1,
    });

    this.gl = this.renderer.gl;
    this.gl.clearColor(0, 0, 0, 0);
    this.gl.enable(this.gl.BLEND);
    this.gl.blendFunc(this.gl.ONE, this.gl.ONE_MINUS_SRC_ALPHA); // premult blend

    const geometry = new Triangle(this.gl);
    this.program = new Program(this.gl, {
      vertex: VERT,
      fragment: FRAG,
      uniforms: {
        iTime:          { value: 0 },
        iResolution:    { value: new Vec3(canvas.width, canvas.height, 1) },
        hue:            { value: 0 },
        hover:          { value: 0 },
        rot:            { value: 0 },
        hoverIntensity: { value: 0 },
        brightness:     { value: 2.5 },
      },
    });

    const mesh = new Mesh(this.gl, { geometry, program: this.program });

    const resize = () => {
      const w   = this.container.clientWidth  || 280;
      const h   = this.container.clientHeight || 280;
      const dpr = window.devicePixelRatio || 1;
      this.renderer.setSize(w * dpr, h * dpr);
      (canvas as HTMLCanvasElement).style.width  = w + "px";
      (canvas as HTMLCanvasElement).style.height = h + "px";
      this.program.uniforms.iResolution.value.set(
        this.gl.canvas.width,
        this.gl.canvas.height,
        this.gl.canvas.width / (this.gl.canvas.height || 1)
      );
    };
    window.addEventListener("resize", resize);
    resize();

    const tick = (t: number) => {
      this.rafId = requestAnimationFrame(tick);
      const dt = Math.min((t - this.lastTime) * 0.001, 0.1);
      this.lastTime = t;
      this.update(t * 0.001, dt);
      this.gl.clear(this.gl.COLOR_BUFFER_BIT);
      this.renderer.render({ scene: mesh });
    };
    this.rafId = requestAnimationFrame(tick);
  }

  // ── Public API ───────────────────────────────────────────────────────────

  public setState(state: OrbState): void {
    if (this.targetState === state) return;
    this.targetState = state;
    this.transitionProgress = 0.0;
    if (state === "WAKE_DETECTED") this.wakeFlash = 1.0;
  }

  public setAudioLevel(level: number): void {
    this.targetAudioLevel = Math.max(0, Math.min(1, level));
  }

  // ── Update loop ──────────────────────────────────────────────────────────

  private update(time: number, dt: number): void {
    this.audioLevel += (this.targetAudioLevel - this.audioLevel) * 0.2;

    if (this.transitionProgress < 1.0) {
      this.transitionProgress = Math.min(1.0, this.transitionProgress + dt * 3.0);
      if (this.transitionProgress >= 1.0) this.currentState = this.targetState;
    }

    const p0 = STATE_PARAMS[this.currentState];
    const p1 = STATE_PARAMS[this.targetState];
    const t  = this.smoothStep(this.transitionProgress);

    const hue            = this.lerp(p0.hue,             p1.hue,             t);
    const baseRotSpeed   = this.lerp(p0.baseRotSpeed,    p1.baseRotSpeed,    t);
    const voiceMult      = this.lerp(p0.voiceMultiplier, p1.voiceMultiplier, t);
    const hoverIntensity = this.lerp(p0.hoverIntensity,  p1.hoverIntensity,  t);
    const hoverBase      = this.lerp(p0.hoverBase,       p1.hoverBase,       t);
    const opacity        = this.lerp(p0.opacity,         p1.opacity,         t);
    const noiseFreq      = this.lerp(p0.noiseFreq,       p1.noiseFreq,       t);
    const brightness     = this.lerp(p0.brightness,      p1.brightness,      t);

    const flashBoost = this.wakeFlash * 2.0;
    if (this.wakeFlash > 0) this.wakeFlash = Math.max(0, this.wakeFlash - dt * 1.8);

    const rotSpeed = baseRotSpeed + this.audioLevel * voiceMult * 2.5 + flashBoost;
    this.currentRot += dt * rotSpeed;

    const targetHover = Math.min(hoverBase + this.audioLevel * 1.8, 1.0);
    this.currentHover += (targetHover - this.currentHover) * Math.min(dt * 8, 1);

    const sp = Math.min(dt * 4, 1);
    this.currentHue            += (hue            - this.currentHue)            * sp;
    this.currentHoverIntensity += (hoverIntensity  - this.currentHoverIntensity) * sp;
    this.currentBrightness     += (brightness      - this.currentBrightness)     * sp;
    this.currentOpacity        += (opacity         - this.currentOpacity)        * Math.min(dt * 5, 1);

    // Drive CSS opacity so IDLE hides the orb
    const canvas = this.gl.canvas as HTMLCanvasElement;
    canvas.style.opacity = String(this.currentOpacity);

    this.program.uniforms.iTime.value          = time * noiseFreq;
    this.program.uniforms.hue.value            = this.currentHue;
    this.program.uniforms.rot.value            = this.currentRot;
    this.program.uniforms.hover.value          = this.currentHover;
    this.program.uniforms.hoverIntensity.value = this.currentHoverIntensity;
    this.program.uniforms.brightness.value     = this.currentBrightness;
  }

  private lerp(a: number, b: number, t: number) { return a + (b - a) * t; }
  private smoothStep(t: number) { return t * t * (3 - 2 * t); }
}
