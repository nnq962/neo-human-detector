type OfferData = {
  iceUfrag: string
  icePwd: string
  medias: string[]
}

export function getWhepUrl(src: string) {
  const trimmed = src.trim()
  if (!trimmed) return ""
  return trimmed.endsWith("/whep")
    ? trimmed
    : `${trimmed.replace(/\/$/, "")}/whep`
}

function unquote(value: string) {
  return value.trim().replace(/^"|"$/g, "")
}

export function parseIceServers(link: string | null): RTCIceServer[] {
  if (!link) return []

  return link
    .split(",")
    .map((entry) => {
      const urlMatch = entry.match(/<([^>]+)>/)
      if (!urlMatch) return null

      const server: RTCIceServer = { urls: urlMatch[1] }
      entry.split(";").forEach((part) => {
        const [key, value] = part.split("=")
        if (key?.trim() === "username") server.username = unquote(value ?? "")
        if (key?.trim() === "credential") server.credential = unquote(value ?? "")
      })
      return server
    })
    .filter((server): server is RTCIceServer => Boolean(server))
}

export function getSessionUrl(response: Response, endpoint: string) {
  const location = response.headers.get("location")
  return location ? new URL(location, endpoint).toString() : ""
}

export function parseOffer(sdp: string): OfferData {
  const offer: OfferData = { iceUfrag: "", icePwd: "", medias: [] }
  sdp.split("\r\n").forEach((line) => {
    if (line.startsWith("m=")) offer.medias.push(line.slice(2))
    if (!offer.iceUfrag && line.startsWith("a=ice-ufrag:")) {
      offer.iceUfrag = line.slice(12)
    }
    if (!offer.icePwd && line.startsWith("a=ice-pwd:")) {
      offer.icePwd = line.slice(10)
    }
  })
  return offer
}

export function generateSdpFragment(
  offer: OfferData,
  candidates: RTCIceCandidate[],
) {
  const byMedia = new Map<number, RTCIceCandidate[]>()
  candidates.forEach((candidate) => {
    if (candidate.sdpMLineIndex === null) return
    byMedia.set(candidate.sdpMLineIndex, [
      ...(byMedia.get(candidate.sdpMLineIndex) ?? []),
      candidate,
    ])
  })

  let fragment = `a=ice-ufrag:${offer.iceUfrag}\r\na=ice-pwd:${offer.icePwd}\r\n`
  offer.medias.forEach((media, mid) => {
    const mediaCandidates = byMedia.get(mid)
    if (!mediaCandidates) return

    fragment += `m=${media}\r\na=mid:${mid}\r\n`
    mediaCandidates.forEach((candidate) => {
      fragment += `a=${candidate.candidate}\r\n`
    })
  })
  return fragment
}
