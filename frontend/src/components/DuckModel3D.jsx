import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { useGLTF, useAnimations } from '@react-three/drei'
import * as THREE from 'three'

/**
 * DuckModel3D — drives the RIGGED duck loaded from /public/duck.glb
 * (Sketchfab "Lowpoly Duck (animated)", CC-BY, wisdom3D).
 *
 * The model ships a single `walkcycle_1` clip and no idle, so: play the walk
 * cycle while moving toward the mouse (turning to face travel direction) and
 * freeze it at its rest frame when still. Camera zooms to the head on focus
 * (password / email). Auto-normalized to the scene's scale + ground.
 */

const lerp = THREE.MathUtils.lerp
const _look = new THREE.Vector3()
const MODEL_URL = '/duck.glb'

// Calibrated for this model (native height ~0.64, Y-up, feet at y≈0):
const TARGET_HEIGHT = 1.6   // world units to scale the duck to
const HEAD_FRAC = 0.86      // head height ÷ model height (camera zoom target)
const FORWARD_OFFSET = Math.PI  // model faces −Z natively, so flip it to face the camera
const WALK_SPEED = 2.2      // world units / sec
const CLIP_TIMESCALE = 1.4  // playback rate of the walk cycle

function lerpAngle(a, b, t) {
  let diff = (b - a) % (Math.PI * 2)
  if (diff > Math.PI) diff -= Math.PI * 2
  if (diff < -Math.PI) diff += Math.PI * 2
  return a + diff * Math.min(1, t)
}

export default function DuckModel3D({ targetXRef, targetZRef, lastMoveRef, expression, guide }) {
  const root = useRef()
  const { scene, animations } = useGLTF(MODEL_URL)
  // Attach the mixer to `root` (which wraps the ORIGINAL scene) — do NOT clone a
  // skinned model with Object3D.clone(), that breaks the skeleton and the mesh
  // won't animate. Single instance, so using the scene directly is fine.
  const { actions, names } = useAnimations(animations, root)
  const facing = useRef(0)
  const zoomRef = useRef(expression ? 1 : 0)

  // Normalize transform (scale to TARGET_HEIGHT, center X/Z, feet on ground)
  // applied to a WRAPPER group so the rigged scene itself is left untouched.
  const norm = useMemo(() => {
    const box = new THREE.Box3().setFromObject(scene)
    const size = new THREE.Vector3(); box.getSize(size)
    const center = new THREE.Vector3(); box.getCenter(center)
    const s = TARGET_HEIGHT / (size.y || 1)
    scene.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false } })
    return { s, pos: [-center.x * s, -box.min.y * s, -center.z * s], headY: TARGET_HEIGHT * HEAD_FRAC }
  }, [scene])
  const headY = norm.headY

  // Single walk clip → play it, but keep it paused (frozen at rest) until moving.
  const walkAction = useMemo(() => actions[names[0]] || Object.values(actions)[0] || null, [actions, names])
  useEffect(() => {
    if (!walkAction) return
    // Keep the clip playing always; freeze it by setting timeScale to 0 when
    // idle (do NOT reset time, or short mouse-follow hops keep restarting the
    // cycle and the legs never visibly step).
    walkAction.reset().play()
    walkAction.timeScale = 0
  }, [walkAction])

  useFrame((state, delta) => {
    if (!root.current) return
    const d = Math.min(0.05, delta)
    const now = performance.now()
    const march = expression === 'march'    // QA: march in place to verify the rig
    const follow = expression === 'follow'  // QA: simulate cursor-follow (sign-in scenario)
    const focused = !!expression && !march && !follow
    if (follow) { targetXRef.current = Math.sin(state.clock.elapsedTime * 0.8) * 1.6; lastMoveRef.current = { t: now } }

    let tx, tz
    if (focused) { tx = root.current.position.x; tz = root.current.position.z }
    else if (lastMoveRef.current.t && now - lastMoveRef.current.t < 2200) { tx = targetXRef.current; tz = targetZRef.current }
    else if (guide) { tx = 1.8; tz = 0 }
    else { tx = 0; tz = 0 }
    tx = Math.max(-2.2, Math.min(2.2, tx))
    tz = Math.max(-0.8, Math.min(0.9, tz))

    const dx = tx - root.current.position.x
    const dz = tz - root.current.position.z
    const dist = Math.hypot(dx, dz)
    let walking = false
    if (dist > 0.05) {
      const stepAmt = Math.min(dist, WALK_SPEED * d)
      root.current.position.x += (dx / dist) * stepAmt
      root.current.position.z += (dz / dist) * stepAmt
      walking = true
      if (Math.abs(dx) > 0.02) facing.current = Math.sign(dx)
    }

    const yawTarget = walking ? Math.atan2(dx, dz) + FORWARD_OFFSET : FORWARD_OFFSET
    root.current.rotation.y = lerpAngle(root.current.rotation.y, yawTarget, d * 9)

    // Keep the walk cycle running the whole time the pointer is active — not just
    // during a single micro-step — so mouse-follow shows a real stride instead of
    // tiny hops. Freeze only once the cursor's been still a while (reading).
    const active = !!lastMoveRef.current.t && now - lastMoveRef.current.t < 1600
    if (walkAction) walkAction.timeScale = (walking || active || march) ? CLIP_TIMESCALE : 0

    // zoom to head on focus
    zoomRef.current = lerp(zoomRef.current, focused ? 1 : 0, d * 4)
    const zf = zoomRef.current
    const hx = root.current.position.x
    const cam = state.camera
    cam.position.set(lerp(0, hx, zf), lerp(1.25, headY + 0.15, zf), lerp(5.1, 2.7, zf))
    _look.set(lerp(0, hx, zf), lerp(0.55, headY, zf), lerp(0, 0.22, zf))
    cam.lookAt(_look)
  })

  return (
    <group ref={root}>
      <group scale={norm.s} position={norm.pos}>
        <primitive object={scene} />
      </group>
    </group>
  )
}

useGLTF.preload(MODEL_URL)
