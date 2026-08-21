export type GlobeCity = {
  name: string
  lat: number
  lng: number
}

/** Capitals of G20 national members + Brussels for the EU. */
export const G20_CAPITALS: GlobeCity[] = [
  { name: "Buenos Aires", lat: -34.6037, lng: -58.3816 },
  { name: "Canberra", lat: -35.2809, lng: 149.13 },
  { name: "Brasília", lat: -15.7975, lng: -47.8919 },
  { name: "Ottawa", lat: 45.4215, lng: -75.6972 },
  { name: "Beijing", lat: 39.9042, lng: 116.4074 },
  { name: "Paris", lat: 48.8566, lng: 2.3522 },
  { name: "Berlin", lat: 52.52, lng: 13.405 },
  { name: "New Delhi", lat: 28.6139, lng: 77.209 },
  { name: "Jakarta", lat: -6.2088, lng: 106.8456 },
  { name: "Rome", lat: 41.9028, lng: 12.4964 },
  { name: "Tokyo", lat: 35.6762, lng: 139.6503 },
  { name: "Mexico City", lat: 19.4326, lng: -99.1332 },
  { name: "Moscow", lat: 55.7558, lng: 37.6173 },
  { name: "Riyadh", lat: 24.7136, lng: 46.6753 },
  { name: "Pretoria", lat: -25.7479, lng: 28.2293 },
  { name: "Seoul", lat: 37.5665, lng: 126.978 },
  { name: "Ankara", lat: 39.9334, lng: 32.8597 },
  { name: "London", lat: 51.5074, lng: -0.1278 },
  { name: "Washington, D.C.", lat: 38.9072, lng: -77.0369 },
  { name: "Brussels", lat: 50.8503, lng: 4.3517 },
]

/** Leading African metro economies by GDP. */
export const AFRICAN_GDP_CITIES: GlobeCity[] = [
  { name: "Johannesburg", lat: -26.2041, lng: 28.0473 },
  { name: "Cairo", lat: 30.0444, lng: 31.2357 },
  { name: "Lagos", lat: 6.5244, lng: 3.3792 },
  { name: "Cape Town", lat: -33.9249, lng: 18.4241 },
  { name: "Nairobi", lat: -1.2921, lng: 36.8219 },
  { name: "Casablanca", lat: 33.5731, lng: -7.5898 },
  { name: "Luanda", lat: -8.839, lng: 13.2894 },
]

/** Remittance-origin hub for spoke arcs. */
export const GLOBE_HUB = AFRICAN_GDP_CITIES[0]!

export function allGlobeCities(): GlobeCity[] {
  const seen = new Set<string>()
  const cities: GlobeCity[] = []
  for (const city of [...G20_CAPITALS, ...AFRICAN_GDP_CITIES]) {
    const coordinateKey = `${city.lat.toFixed(3)},${city.lng.toFixed(3)}`
    if (seen.has(coordinateKey)) continue
    seen.add(coordinateKey)
    cities.push(city)
  }
  return cities
}
