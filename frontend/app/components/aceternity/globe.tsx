import { useEffect, useRef, useState } from "react"
import {
  Color,
  Fog,
  Group,
  MeshPhongMaterial,
  PerspectiveCamera,
  Vector3,
  type Material,
} from "three"
import ThreeGlobe from "three-globe"
import { useThree, Canvas, extend } from "@react-three/fiber"
import { OrbitControls } from "@react-three/drei"
import countries from "~/data/globe.json"

declare module "@react-three/fiber" {
  interface ThreeElements {
    threeGlobe: ThreeElements["mesh"] & {
      new (): ThreeGlobe
    }
  }
}

extend({ ThreeGlobe: ThreeGlobe })

const RING_PROPAGATION_SPEED = 3
const aspect = 1.2
/** Far enough that atmosphere fits inside the (oversized) canvas. */
const cameraZ = 360

type Position = {
  order: number
  startLat: number
  startLng: number
  endLat: number
  endLng: number
  arcAlt: number
  color: string
}

type GlobePoint = {
  size: number
  order: number
  color: string
  lat: number
  lng: number
}

export type GlobeConfig = {
  pointSize?: number
  globeColor?: string
  showAtmosphere?: boolean
  atmosphereColor?: string
  atmosphereAltitude?: number
  emissive?: string
  emissiveIntensity?: number
  shininess?: number
  polygonColor?: string
  ambientLight?: string
  directionalLeftLight?: string
  directionalTopLight?: string
  pointLight?: string
  arcTime?: number
  arcLength?: number
  rings?: number
  maxRings?: number
  initialPosition?: {
    lat: number
    lng: number
  }
  autoRotate?: boolean
  autoRotateSpeed?: number
  fogColor?: string
}

interface WorldProps {
  globeConfig: GlobeConfig
  data: Position[]
}

function isPosition(value: object): value is Position {
  return (
    "order" in value &&
    "startLat" in value &&
    "startLng" in value &&
    "endLat" in value &&
    "endLng" in value &&
    "arcAlt" in value &&
    "color" in value &&
    typeof value.order === "number" &&
    typeof value.startLat === "number" &&
    typeof value.startLng === "number" &&
    typeof value.endLat === "number" &&
    typeof value.endLng === "number" &&
    typeof value.arcAlt === "number" &&
    typeof value.color === "string"
  )
}

function isGlobePoint(value: object): value is GlobePoint {
  return (
    "lat" in value &&
    "lng" in value &&
    "color" in value &&
    typeof value.lat === "number" &&
    typeof value.lng === "number" &&
    typeof value.color === "string"
  )
}

function isMeshPhongMaterial(
  material: Material
): material is MeshPhongMaterial {
  return material instanceof MeshPhongMaterial
}

function readArcStartLat(value: object): number {
  if (!isPosition(value)) return 0
  return value.startLat
}

function readArcStartLng(value: object): number {
  if (!isPosition(value)) return 0
  return value.startLng
}

function readArcEndLat(value: object): number {
  if (!isPosition(value)) return 0
  return value.endLat
}

function readArcEndLng(value: object): number {
  if (!isPosition(value)) return 0
  return value.endLng
}

function readArcColor(value: object): string {
  if (!isPosition(value)) return "#000000"
  return value.color
}

function readArcAltitude(value: object): number {
  if (!isPosition(value)) return 0
  return value.arcAlt
}

function readArcOrder(value: object): number {
  if (!isPosition(value)) return 0
  return value.order
}

function readPointColor(value: object): string {
  if (!isGlobePoint(value)) return "#000000"
  return value.color
}

export function Globe({ globeConfig, data }: WorldProps) {
  const globeRef = useRef<ThreeGlobe | null>(null)
  const groupRef = useRef<Group | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)

  const defaultProps = {
    pointSize: 1,
    atmosphereColor: "#ffffff",
    showAtmosphere: true,
    atmosphereAltitude: 0.1,
    polygonColor: "rgba(255,255,255,0.7)",
    globeColor: "#1d072e",
    emissive: "#000000",
    emissiveIntensity: 0.1,
    shininess: 0.9,
    arcTime: 2000,
    arcLength: 0.9,
    rings: 1,
    maxRings: 3,
    ...globeConfig,
  }

  // Initialize globe only once
  useEffect(() => {
    if (!globeRef.current && groupRef.current) {
      const globe = new ThreeGlobe()
      globeRef.current = globe
      groupRef.current.add(globe)
      setIsInitialized(true)
    }
  }, [])

  // Build material when globe is initialized or when relevant props change
  useEffect(() => {
    if (!globeRef.current || !isInitialized) return

    const globeMaterial = globeRef.current.globeMaterial()
    if (!isMeshPhongMaterial(globeMaterial)) return

    globeMaterial.color = new Color(globeConfig.globeColor)
    globeMaterial.emissive = new Color(globeConfig.emissive)
    globeMaterial.emissiveIntensity = globeConfig.emissiveIntensity || 0.1
    globeMaterial.shininess = globeConfig.shininess || 0.9
  }, [
    isInitialized,
    globeConfig.globeColor,
    globeConfig.emissive,
    globeConfig.emissiveIntensity,
    globeConfig.shininess,
  ])

  // Build data when globe is initialized or when data changes
  useEffect(() => {
    if (!globeRef.current || !isInitialized || !data) return

    const arcs = data
    const points: GlobePoint[] = []
    for (let index = 0; index < arcs.length; index++) {
      const globeArc = arcs[index]
      if (!globeArc) continue
      points.push({
        size: defaultProps.pointSize,
        order: globeArc.order,
        color: globeArc.color,
        lat: globeArc.startLat,
        lng: globeArc.startLng,
      })
      points.push({
        size: defaultProps.pointSize,
        order: globeArc.order,
        color: globeArc.color,
        lat: globeArc.endLat,
        lng: globeArc.endLng,
      })
    }

    // remove duplicates for same lat and lng
    const filteredPoints = points.filter(
      (point, pointIndex, allPoints) =>
        allPoints.findIndex(
          (other) => other.lat === point.lat && other.lng === point.lng
        ) === pointIndex
    )

    globeRef.current
      .hexPolygonsData(countries.features)
      .hexPolygonResolution(3)
      .hexPolygonMargin(0.7)
      .showAtmosphere(defaultProps.showAtmosphere)
      .atmosphereColor(defaultProps.atmosphereColor)
      .atmosphereAltitude(defaultProps.atmosphereAltitude)
      .hexPolygonColor(() => defaultProps.polygonColor)

    globeRef.current
      .arcsData(data)
      .arcStartLat(readArcStartLat)
      .arcStartLng(readArcStartLng)
      .arcEndLat(readArcEndLat)
      .arcEndLng(readArcEndLng)
      .arcColor(readArcColor)
      .arcAltitude(readArcAltitude)
      .arcStroke(() => [0.32, 0.28, 0.3][Math.round(Math.random() * 2)] ?? 0.3)
      .arcDashLength(defaultProps.arcLength)
      .arcDashInitialGap(readArcOrder)
      .arcDashGap(15)
      .arcDashAnimateTime(() => defaultProps.arcTime)

    globeRef.current
      .pointsData(filteredPoints)
      .pointColor(readPointColor)
      .pointsMerge(true)
      .pointAltitude(0.0)
      .pointRadius(2)

    globeRef.current
      .ringsData([])
      .ringColor(() => defaultProps.polygonColor)
      .ringMaxRadius(defaultProps.maxRings)
      .ringPropagationSpeed(RING_PROPAGATION_SPEED)
      .ringRepeatPeriod(
        (defaultProps.arcTime * defaultProps.arcLength) / defaultProps.rings
      )
  }, [
    isInitialized,
    data,
    defaultProps.pointSize,
    defaultProps.showAtmosphere,
    defaultProps.atmosphereColor,
    defaultProps.atmosphereAltitude,
    defaultProps.polygonColor,
    defaultProps.arcLength,
    defaultProps.arcTime,
    defaultProps.rings,
    defaultProps.maxRings,
  ])

  // Handle rings animation with cleanup
  useEffect(() => {
    if (!globeRef.current || !isInitialized || !data) return

    const interval = setInterval(() => {
      if (!globeRef.current) return

      const newNumbersOfRings = genRandomNumbers(
        0,
        data.length,
        Math.floor((data.length * 4) / 5)
      )

      const ringsData = data
        .filter((_globeArc, index) => newNumbersOfRings.includes(index))
        .map((globeArc) => ({
          lat: globeArc.startLat,
          lng: globeArc.startLng,
          color: globeArc.color,
        }))

      globeRef.current.ringsData(ringsData)
    }, 2000)

    return () => {
      clearInterval(interval)
    }
  }, [isInitialized, data])

  return <group ref={groupRef} />
}

export function WebGLRendererConfig() {
  const { gl: renderer, size } = useThree()

  useEffect(() => {
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.setSize(size.width, size.height)
    renderer.setClearColor(0x000000, 0)
  }, [renderer, size.height, size.width])

  return null
}

function SceneFog({ color }: { color: string }) {
  const { scene } = useThree()

  useEffect(() => {
    scene.fog = new Fog(new Color(color).getHex(), 420, 2200)
  }, [scene, color])

  return null
}

export function World(props: WorldProps) {
  const { globeConfig } = props
  const fogColor = globeConfig.fogColor ?? "#F8FAFC"

  return (
    <Canvas
      camera={new PerspectiveCamera(50, aspect, 180, 1800)}
      gl={{ alpha: true, antialias: true }}
      style={{ background: "transparent" }}
    >
      <WebGLRendererConfig />
      <SceneFog color={fogColor} />
      <ambientLight color={globeConfig.ambientLight} intensity={0.65} />
      <directionalLight
        color={globeConfig.directionalLeftLight}
        position={new Vector3(-400, 100, 400)}
      />
      <directionalLight
        color={globeConfig.directionalTopLight}
        position={new Vector3(-200, 500, 200)}
      />
      <pointLight
        color={globeConfig.pointLight}
        position={new Vector3(-200, 500, 200)}
        intensity={0.8}
      />
      <Globe {...props} />
      <OrbitControls
        enablePan={false}
        enableZoom={false}
        minDistance={cameraZ}
        maxDistance={cameraZ}
        autoRotateSpeed={1}
        autoRotate={true}
        minPolarAngle={Math.PI / 3.5}
        maxPolarAngle={Math.PI - Math.PI / 3}
      />
    </Canvas>
  )
}

export function genRandomNumbers(
  minimum: number,
  maximum: number,
  count: number
) {
  const numbers: number[] = []
  while (numbers.length < count) {
    const candidate = Math.floor(Math.random() * (maximum - minimum)) + minimum
    if (numbers.indexOf(candidate) === -1) numbers.push(candidate)
  }

  return numbers
}
