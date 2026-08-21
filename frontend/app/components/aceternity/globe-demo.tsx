import { World, type GlobeConfig } from "~/components/aceternity/globe"
import {
  AFRICAN_GDP_CITIES,
  GLOBE_HUB,
  allGlobeCities,
  type GlobeCity,
} from "~/data/globe-cities"
import { useThemeColors, type ThemeColors } from "~/lib/use-theme-colors"

type GlobeArc = {
  order: number
  startLat: number
  startLng: number
  endLat: number
  endLng: number
  arcAlt: number
  color: string
}

const ARC_ALT = 0.2
const ARC_ALT_RETURN = 0.28

function spoke(
  from: GlobeCity,
  to: GlobeCity,
  color: string,
  order: number
): GlobeArc[] {
  return [
    {
      order,
      startLat: from.lat,
      startLng: from.lng,
      endLat: to.lat,
      endLng: to.lng,
      arcAlt: ARC_ALT,
      color,
    },
    {
      order: order + 1,
      startLat: to.lat,
      startLng: to.lng,
      endLat: from.lat,
      endLng: from.lng,
      arcAlt: ARC_ALT_RETURN,
      color,
    },
  ]
}

/** Johannesburg spokes + African ring — every city appears as an endpoint. */
function buildArcs(color: string): GlobeArc[] {
  const arcs: GlobeArc[] = []
  let order = 1

  for (const city of allGlobeCities()) {
    if (city.name === GLOBE_HUB.name) continue
    arcs.push(...spoke(GLOBE_HUB, city, color, order))
    order += 2
  }

  for (let index = 0; index < AFRICAN_GDP_CITIES.length; index++) {
    const startCity = AFRICAN_GDP_CITIES[index]!
    const endCity = AFRICAN_GDP_CITIES[(index + 1) % AFRICAN_GDP_CITIES.length]!
    if (startCity.name === GLOBE_HUB.name || endCity.name === GLOBE_HUB.name) {
      continue
    }
    arcs.push(...spoke(startCity, endCity, color, order))
    order += 2
  }

  return arcs
}

function buildGlobeConfig(
  colors: ThemeColors & { scheme?: "light" | "dark" }
): GlobeConfig {
  const dark = colors.scheme === "dark"
  return {
    pointSize: 3,
    globeColor: colors.globe,
    emissive: colors.globe,
    emissiveIntensity: dark ? 0.35 : 0.12,
    shininess: dark ? 0.7 : 0.5,
    showAtmosphere: true,
    atmosphereColor: dark ? colors.foreground : colors.background,
    atmosphereAltitude: 0.1,
    polygonColor: colors.land,
    ambientLight: colors.light,
    directionalLeftLight: colors.light,
    directionalTopLight: colors.light,
    pointLight: colors.light,
    fogColor: colors.background,
    arcTime: 1000,
    arcLength: 0.9,
    rings: 1,
    maxRings: 4,
    initialPosition: { lat: GLOBE_HUB.lat, lng: GLOBE_HUB.lng },
    autoRotate: true,
    autoRotateSpeed: 0.4,
  }
}

export default function GlobeDemo() {
  const colors = useThemeColors()
  const arcs = buildArcs(colors.primary)
  const worldKey = `${colors.scheme}:${colors.globe}:${colors.land}:${colors.primary}:${colors.light}`

  return (
    <div className="absolute inset-0 size-full">
      <World
        key={worldKey}
        globeConfig={buildGlobeConfig(colors)}
        data={arcs}
      />
    </div>
  )
}
