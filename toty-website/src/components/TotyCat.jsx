import './TotyCat.css'

export default function TotyCat({ size = 100, className = '', animate = true }) {
  return (
    <div
      className={`toty-pet ${animate ? 'float-animation' : ''} ${className}`}
      style={{ width: size, height: size }}
    >
      <img
        src="/toty-pet-animated.gif"
        alt="Toty"
        className="toty-pet-img"
        draggable={false}
        loading="lazy"
      />
    </div>
  )
}
