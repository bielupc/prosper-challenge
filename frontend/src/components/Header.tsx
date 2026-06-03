export default function Header() {
  return (
    <header className="bg-white border-b border-border-gray">
      <div className="max-w-[1200px] mx-auto px-8 py-4 flex items-center gap-3">
        <img src="/logo.svg" alt="Prosper" className="h-7 w-auto" />
        <span className="text-border-cream select-none">·</span>
        <span className="font-manrope text-warm-500 text-sm">EHR Dashboard</span>
      </div>
    </header>
  )
}
