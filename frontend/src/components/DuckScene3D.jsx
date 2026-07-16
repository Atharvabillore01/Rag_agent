import { useEffect, useRef, Suspense, Component } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import DuckModel3D from './DuckModel3D'

/**
 * DuckScene3D — a small 3D duck companion in a grass field (three.js / r3f).
 *
 * Built procedurally from primitives (no model file → works offline / strict CSP).
 * The duck FACES the viewer. It walks sideways toward the mouse with a waddle,
 * reads a book when idle, and on password focus raises its wings over its eyes
 * (`expression="cover"`; `"peek"` = revealed). On register, `guide` sends it
 * toward the sign-up form. Use as an absolute background layer.
 */

const WHITE = '#F7F9FC'
const WHITE_SHADE = '#DCE3EF'
const ORANGE = '#F2870E'
const ORANGE_DK = '#D96C08'
const EYE = '#152444'
const lerp = THREE.MathUtils.lerp
const _look = new THREE.Vector3()

// Shortest-path angle lerp so the duck turns the short way, never spins around.
function lerpAngle(a, b, t) {
  let diff = (b - a) % (Math.PI * 2)
  if (diff > Math.PI) diff -= Math.PI * 2
  if (diff < -Math.PI) diff += Math.PI * 2
  return a + diff * Math.min(1, t)
}

function Duck({ targetXRef, targetZRef, lastMoveRef, expression, guide }) {
  const root = useRef()
  const body = useRef()
  const head = useRef()
  const legL = useRef()
  const legR = useRef()
  const wingL = useRef()
  const wingR = useRef()
  const eyeL = useRef()
  const eyeR = useRef()
  const book = useRef()
  const facing = useRef(0)
  // Initialize toward the target so a forced pose (?duck=…) renders settled.
  const cover = useRef(expression === 'cover' ? 1 : expression === 'peek' ? 0.62 : 0)
  const zoom = useRef(expression ? 1 : 0)

  useFrame((state, delta) => {
    if (!root.current) return
    const t = state.clock.elapsedTime
    const d = Math.min(0.05, delta)
    const covering = expression === 'cover' || expression === 'peek'
    const now = performance.now()

    // targets: x = across the field, z = depth (toward the camera/screen)
    const focused = !!expression
    let tx, tz
    if (focused) { tx = root.current.position.x; tz = root.current.position.z } // freeze while a field is focused
    else if (lastMoveRef.current.t && now - lastMoveRef.current.t < 2200) { tx = targetXRef.current; tz = targetZRef.current }
    else if (guide) { tx = 1.8; tz = 0 }
    else { tx = 0; tz = 0 }
    tx = Math.max(-2.2, Math.min(2.2, tx))
    tz = Math.max(-0.8, Math.min(0.9, tz))  // gentle depth — don't let it balloon

    // walk toward the target in the ground plane (x + z)
    const dx = tx - root.current.position.x
    const dz = tz - root.current.position.z
    const dist = Math.hypot(dx, dz)
    let walking = false
    if (dist > 0.05) {
      const stepAmt = Math.min(dist, 2.4 * d)
      root.current.position.x += (dx / dist) * stepAmt
      root.current.position.z += (dz / dist) * stepAmt
      walking = true
      if (Math.abs(dx) > 0.02) facing.current = Math.sign(dx)
    }
    const reading = !covering && !walking

    // A real duck walk: TURN to face the direction of travel and waddle forward,
    // then turn back to face the camera when idle/focused (so it reads/covers
    // facing you). This kills the sideways "crab walk".
    const yawTarget = walking ? Math.atan2(dx, dz) : 0
    root.current.rotation.y = lerpAngle(root.current.rotation.y, yawTarget, d * 9)

    const step = t * 8
    if (walking) {
      root.current.position.y = Math.abs(Math.sin(step)) * 0.12   // step hop
      body.current.rotation.z = Math.sin(step) * 0.16             // side-to-side waddle roll
      body.current.rotation.y = Math.sin(step * 0.5) * 0.07       // gentle waddle sway
      legL.current.rotation.x = Math.sin(step) * 0.85             // legs step (forward now)
      legR.current.rotation.x = -Math.sin(step) * 0.85
      head.current.position.z = 0.42 + Math.max(0, Math.sin(step)) * 0.06  // head bob
    } else {
      root.current.position.y = lerp(root.current.position.y, 0, 0.12)
      body.current.rotation.z = lerp(body.current.rotation.z, 0, 0.15)
      body.current.rotation.y = lerp(body.current.rotation.y, 0, 0.15)
      body.current.position.y = 0.8 + Math.sin(t * 1.6) * 0.02
      legL.current.rotation.x = lerp(legL.current.rotation.x, 0, 0.15)
      legR.current.rotation.x = lerp(legR.current.rotation.x, 0, 0.15)
      head.current.position.z = lerp(head.current.position.z, 0.42, 0.15)
    }

    // head tilt: glance down a touch while reading (keep the face visible)
    head.current.rotation.x = lerp(head.current.rotation.x, reading ? 0.2 : 0, d * 8)

    // close the eyes (flatten to slits) while fully covering for the password
    if (eyeL.current && eyeR.current) {
      const sy = lerp(eyeL.current.scale.y, expression === 'cover' ? 0.14 : 1, d * 12)
      eyeL.current.scale.y = sy
      eyeR.current.scale.y = sy
    }

    // book appears while reading
    const bookScale = lerp(book.current.scale.x, reading ? 1 : 0.001, d * 10)
    book.current.scale.setScalar(bookScale)
    book.current.visible = bookScale > 0.02

    // wings: cover eyes / hold book / rest
    const c0 = expression === 'cover' ? 1 : expression === 'peek' ? 0.62 : 0
    cover.current = lerp(cover.current, c0, d * 10)
    const c = cover.current
    const holding = reading ? 1 : 0
    // left wing
    poseWing(wingL.current, {
      restPos: [0.58, 0.82, 0.02], restRot: [0, 1.5, 0],
      readPos: [0.34, 0.6, 0.7], readRot: [0.5, 0.7, 0],
      coverPos: [0.2, 1.48, 1.02], coverRot: [0.2, 0, 0.5],
    }, c, holding, +1)
    poseWing(wingR.current, {
      restPos: [-0.58, 0.82, 0.02], restRot: [0, -1.5, 0],
      readPos: [-0.34, 0.6, 0.7], readRot: [0.5, -0.7, 0],
      coverPos: [-0.2, 1.48, 1.02], coverRot: [0.2, 0, -0.5],
    }, c, holding, -1)

    // Zoom the camera into the duck's head whenever a field is focused, so the
    // eye-cover (password) / watching (email) reads as a close-up. Return to the
    // wide field view otherwise.
    zoom.current = lerp(zoom.current, focused ? 1 : 0, d * 4)
    const zf = zoom.current
    const hx = root.current.position.x
    // head sits at ~world (hx, 0.78, 0.22) — on focus, zoom RIGHT in so the big
    // head fills the frame (eyes covered for the password).
    const cam = state.camera
    cam.position.set(lerp(0, hx, zf), lerp(1.25, 1.0, zf), lerp(5.1, 2.7, zf))
    _look.set(lerp(0, hx, zf), lerp(0.55, 0.72, zf), lerp(0, 0.22, zf))
    cam.lookAt(_look)
  })

  const eyesClosed = expression === 'cover'
  return (
    <group ref={root} position={[0, 0, 0]} scale={0.52}>
      {/* upright egg body (slimmer, less round) */}
      <mesh ref={body} position={[0, 0.8, 0]} scale={[0.86, 1.08, 0.95]} castShadow>
        <sphereGeometry args={[0.82, 40, 32]} />
        <meshStandardMaterial color={WHITE} roughness={0.72} />
      </mesh>
      <mesh position={[0, 0.56, 0.4]} scale={[0.66, 0.7, 0.7]}>
        <sphereGeometry args={[0.82, 32, 24]} />
        <meshStandardMaterial color={WHITE_SHADE} roughness={0.85} />
      </mesh>
      {/* tail (back, up) */}
      <mesh position={[0, 1.02, -1.02]} rotation={[-0.7, 0, 0]}>
        <coneGeometry args={[0.26, 0.5, 16]} />
        <meshStandardMaterial color={WHITE} roughness={0.72} />
      </mesh>
      {/* short neck */}
      <mesh position={[0, 1.12, 0.34]} rotation={[0.2, 0, 0]}>
        <cylinderGeometry args={[0.3, 0.42, 0.5, 20]} />
        <meshStandardMaterial color={WHITE} roughness={0.72} />
      </mesh>

      {/* HEAD faces +z (camera) */}
      <group ref={head} position={[0, 1.42, 0.42]}>
        <mesh castShadow>
          <sphereGeometry args={[0.46, 36, 28]} />
          <meshStandardMaterial color={WHITE} roughness={0.7} />
        </mesh>
        {/* eyes (flatten to closed slits when covering) */}
        <mesh ref={eyeL} position={[0.17, 0.1, 0.38]} scale={[1, eyesClosed ? 0.14 : 1, 1]}><sphereGeometry args={[0.075, 18, 14]} /><meshStandardMaterial color={EYE} roughness={0.35} /></mesh>
        <mesh ref={eyeR} position={[-0.17, 0.1, 0.38]} scale={[1, eyesClosed ? 0.14 : 1, 1]}><sphereGeometry args={[0.075, 18, 14]} /><meshStandardMaterial color={EYE} roughness={0.35} /></mesh>
        <mesh position={[0.195, 0.13, 0.43]}><sphereGeometry args={[0.024, 8, 8]} /><meshStandardMaterial color="#fff" emissive="#fff" emissiveIntensity={0.5} /></mesh>
        <mesh position={[-0.145, 0.13, 0.43]}><sphereGeometry args={[0.024, 8, 8]} /><meshStandardMaterial color="#fff" emissive="#fff" emissiveIntensity={0.5} /></mesh>
        {/* beak (+z) */}
        <mesh position={[0, -0.06, 0.5]} rotation={[0.12, 0, 0]}><boxGeometry args={[0.34, 0.12, 0.4]} /><meshStandardMaterial color={ORANGE} roughness={0.5} /></mesh>
        <mesh position={[0, -0.15, 0.46]} rotation={[0.12, 0, 0]}><boxGeometry args={[0.28, 0.08, 0.34]} /><meshStandardMaterial color={ORANGE_DK} roughness={0.5} /></mesh>
      </group>

      {/* wings — flat paddles: folded on the flanks, swing FLAT over the eyes to cover */}
      <mesh ref={wingL} position={[0.58, 0.82, 0.02]} rotation={[0, 1.5, 0]} scale={[0.4, 0.5, 0.18]}>
        <sphereGeometry args={[0.62, 24, 18]} /><meshStandardMaterial color={WHITE} roughness={0.72} />
      </mesh>
      <mesh ref={wingR} position={[-0.58, 0.82, 0.02]} rotation={[0, -1.5, 0]} scale={[0.4, 0.5, 0.18]}>
        <sphereGeometry args={[0.62, 24, 18]} /><meshStandardMaterial color={WHITE} roughness={0.72} />
      </mesh>

      {/* book (idle reading) — a clear open book held up in front, pages toward camera.
          Starts hidden if a field is already focused so it stows immediately. */}
      <group ref={book} position={[0, 0.74, 1.0]} rotation={[0.5, 0, 0]} scale={expression ? 0.001 : 1}>
        {/* blue cover underneath */}
        <mesh position={[0, -0.05, 0]}><boxGeometry args={[1.12, 0.08, 0.74]} /><meshStandardMaterial color="#1D4ED8" roughness={0.5} /></mesh>
        {/* white pages, slight open-V */}
        <mesh position={[-0.29, 0.02, 0]} rotation={[0, 0, 0.12]}><boxGeometry args={[0.52, 0.05, 0.66]} /><meshStandardMaterial color="#F6F9FF" roughness={0.7} /></mesh>
        <mesh position={[0.29, 0.02, 0]} rotation={[0, 0, -0.12]}><boxGeometry args={[0.52, 0.05, 0.66]} /><meshStandardMaterial color="#F6F9FF" roughness={0.7} /></mesh>
        {/* spine */}
        <mesh position={[0, 0.03, 0]}><boxGeometry args={[0.07, 0.07, 0.7]} /><meshStandardMaterial color="#0E2E7E" roughness={0.5} /></mesh>
        {/* page lines */}
        {[-0.18, -0.02, 0.14].map((z, i) => (
          <mesh key={i} position={[-0.29, 0.06, z]}><boxGeometry args={[0.4, 0.012, 0.03]} /><meshStandardMaterial color="#B9C7E8" /></mesh>
        ))}
        {[-0.18, -0.02, 0.14].map((z, i) => (
          <mesh key={`r${i}`} position={[0.29, 0.06, z]}><boxGeometry args={[0.4, 0.012, 0.03]} /><meshStandardMaterial color="#B9C7E8" /></mesh>
        ))}
      </group>

      {/* legs + webbed feet — set forward so they peek out in front on the grass */}
      <group ref={legL} position={[0.24, 0.24, 0.72]}>
        <mesh position={[0, -0.1, -0.02]} rotation={[0.4, 0, 0]}><cylinderGeometry args={[0.055, 0.07, 0.3, 12]} /><meshStandardMaterial color={ORANGE} roughness={0.5} /></mesh>
        <mesh position={[0, -0.22, 0.16]} scale={[0.92, 0.22, 1.5]}><sphereGeometry args={[0.18, 18, 12]} /><meshStandardMaterial color={ORANGE} roughness={0.55} /></mesh>
      </group>
      <group ref={legR} position={[-0.24, 0.24, 0.72]}>
        <mesh position={[0, -0.1, -0.02]} rotation={[0.4, 0, 0]}><cylinderGeometry args={[0.055, 0.07, 0.3, 12]} /><meshStandardMaterial color={ORANGE} roughness={0.5} /></mesh>
        <mesh position={[0, -0.22, 0.16]} scale={[0.92, 0.22, 1.5]}><sphereGeometry args={[0.18, 18, 12]} /><meshStandardMaterial color={ORANGE} roughness={0.55} /></mesh>
      </group>
    </group>
  )
}

// blend a wing between rest → reading-hold → cover-eyes poses
function poseWing(mesh, p, cover, holding, side) {
  if (!mesh) return
  // base = rest, blend toward read when holding, then override toward cover
  const bp = p.restPos.map((v, i) => lerp(v, p.readPos[i], holding))
  const br = p.restRot.map((v, i) => lerp(v, p.readRot[i], holding))
  const fp = bp.map((v, i) => lerp(v, p.coverPos[i], cover))
  const fr = br.map((v, i) => lerp(v, p.coverRot[i], cover))
  mesh.position.set(fp[0], fp[1], fp[2])
  mesh.rotation.set(fr[0], fr[1], fr[2])
}

function Grass() {
  const blades = []
  const rng = (i, a, b) => a + (((Math.sin(i * 127.1) * 43758.5) % 1) + 1) % 1 * (b - a)
  for (let i = 0; i < 42; i++) {
    const x = rng(i + 1, -7, 7)
    const z = rng(i + 100, -2, 2)
    const h = rng(i + 50, 0.22, 0.5)
    blades.push(
      <mesh key={i} position={[x, h / 2, z]} rotation={[0, rng(i + 7, 0, 6.28), 0]}>
        <coneGeometry args={[0.055, h, 5]} />
        <meshStandardMaterial color={i % 5 === 0 ? '#3fae63' : '#2f9151'} roughness={0.9} />
      </mesh>
    )
  }
  return <group>{blades}</group>
}

// If the rigged /duck.glb model fails to load (missing file, decode error),
// fall back to the hand-built procedural duck so the scene never breaks.
class ModelBoundary extends Component {
  constructor(props) { super(props); this.state = { failed: false } }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

function Scene({ duckProps }) {
  return (
    <>
      <ambientLight intensity={0.8} />
      <directionalLight position={[3, 8, 6]} intensity={1.5} castShadow shadow-mapSize={[1024, 1024]} shadow-camera-far={30} />
      <directionalLight position={[-6, 4, -3]} intensity={0.3} color="#bfe0ff" />
      <hemisphereLight args={['#dfeecf', '#2a6b3d', 0.5]} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[60, 40]} />
        <meshStandardMaterial color="#2f9151" roughness={1} />
      </mesh>
      <Grass />
      <ModelBoundary fallback={<Duck {...duckProps} />}>
        <Suspense fallback={<Duck {...duckProps} />}>
          <DuckModel3D {...duckProps} />
        </Suspense>
      </ModelBoundary>
      <fog attach="fog" args={['#3d8f5f', 9, 22]} />
    </>
  )
}

export default function DuckScene3D({ expression = null, guide = false, className = '' }) {
  if (typeof window !== 'undefined') {
    const q = new URLSearchParams(window.location.search).get('duck')
    if (q) expression = q
  }
  const wrapRef = useRef(null)
  const targetXRef = useRef(0)
  const targetZRef = useRef(0)
  const lastMoveRef = useRef({ t: 0 })

  useEffect(() => {
    function onMove(e) {
      const el = wrapRef.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const nx = ((e.clientX - r.left) / r.width) * 2 - 1
      const ny = Math.max(0, Math.min(1, (e.clientY - r.top) / r.height))
      targetXRef.current = Math.max(-1, Math.min(1, nx)) * 3
      // pointer toward the bottom/front → duck walks toward the screen (grows)
      targetZRef.current = lerp(-1, 1.5, ny)
      lastMoveRef.current = { t: performance.now() }
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  return (
    <div ref={wrapRef} className={`absolute inset-0 overflow-hidden ${className}`}>
      <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg,#173f31 0%,#256a4c 42%,#3d8f5f 80%)' }} />
      <div className="absolute -top-16 -right-10 w-[420px] h-[420px] rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(255,224,150,0.35) 0%, transparent 70%)' }} />
      {/* Canvas confined to the lower band so the duck lives in the grass and
          never overlaps the heading/text in the upper part of the panel. */}
      <Canvas shadows dpr={[1, 2]} camera={{ position: [0, 1.25, 5.1], fov: 42 }}
        onCreated={({ camera }) => camera.lookAt(0, 0.55, 0)}
        gl={{ alpha: true, antialias: true }}
        style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: '62%' }}>
        <Scene duckProps={{ targetXRef, targetZRef, lastMoveRef, expression, guide }} />
      </Canvas>
    </div>
  )
}
