import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

interface SiteMapProps {
  latitude: number;
  longitude: number;
  siteName?: string;
  height?: string;
}

export function SiteMap({ latitude, longitude, siteName, height = "300px" }: SiteMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!mapRef.current || instanceRef.current) return;

    const map = L.map(mapRef.current, {
      center: [latitude, longitude],
      zoom: 15,
      zoomControl: true,
      scrollWheelZoom: false,
    });

    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a>",
      maxZoom: 19,
    }).addTo(map);

    L.marker([latitude, longitude])
      .addTo(map)
      .bindPopup(siteName || "Site Location");

    instanceRef.current = map;

    return () => {
      map.remove();
      instanceRef.current = null;
    };
  }, [latitude, longitude, siteName]);

  return <div ref={mapRef} style={{ width: "100%", height, borderRadius: "8px" }} />;
}
