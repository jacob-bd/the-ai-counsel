export default function ModelVisualIcon({ visuals, alt = '', scale = 0.72 }) {
  if (visuals?.logo) {
    return (
      <img
        src={visuals.logo}
        alt={alt}
        aria-hidden={alt ? undefined : true}
        style={{
          width: `${scale * 100}%`,
          height: `${scale * 100}%`,
          objectFit: 'contain',
          display: 'block',
        }}
      />
    );
  }

  return visuals?.icon || '?';
}
