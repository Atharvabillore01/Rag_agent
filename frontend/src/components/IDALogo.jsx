const IDA_LOGO_URL = 'https://www.idaindore.org/assets/img/logo.png'

export default function IDALogo({ size = 'md', white = false }) {
  const cfg = {
    sm: { h: 38, titlePx: 18, subPx: 10, gap: 10 },
    md: { h: 46, titlePx: 22, subPx: 11, gap: 12 },
    lg: { h: 58, titlePx: 27, subPx: 13, gap: 14 },
    xl: { h: 72, titlePx: 34, subPx: 15, gap: 16 },
  }
  const { h, titlePx, subPx, gap } = cfg[size] || cfg.md

  return (
    <div className="flex items-center" style={{ gap }}>
      {/* Real IDA government seal logo */}
      <img
        src={IDA_LOGO_URL}
        alt="Indore Development Authority Seal"
        style={{ height: h, width: 'auto' }}
        className="object-contain flex-shrink-0 drop-shadow-sm"
        onError={e => {
          // SVG fallback if image fails to load
          e.currentTarget.style.display = 'none'
          e.currentTarget.nextSibling?.setAttribute('data-fallback', 'true')
        }}
      />

      {/* Text identity */}
      <div>
        <p
          style={{ fontSize: titlePx, letterSpacing: '-0.3px' }}
          className={`font-display font-extrabold leading-none ${white ? 'text-white' : 'text-ida-navy'}`}
        >
          IDA
        </p>
        <p
          style={{ fontSize: subPx }}
          className={`font-medium leading-tight mt-0.5 ${white ? 'text-white/60' : 'text-slate-500'}`}
        >
          Indore Development Authority
        </p>
        {/* Saffron underline accent */}
        <div
          style={{ width: titlePx * 1.9, height: 2, marginTop: 3, borderRadius: 1,
                   background: white ? 'rgba(245,166,35,0.85)' : '#E05D0D' }}
        />
      </div>
    </div>
  )
}
