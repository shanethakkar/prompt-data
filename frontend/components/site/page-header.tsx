export function PageHeader({
  eyebrow,
  title,
  lede,
}: {
  eyebrow: string;
  title: string;
  lede: string;
}) {
  return (
    <div className="mb-10 max-w-2xl">
      <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-primary/90">
        {eyebrow}
      </div>
      <h1 className="mt-3 text-balance text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
        {title}
      </h1>
      <p className="mt-3 text-pretty text-[15px] leading-relaxed text-muted-foreground">{lede}</p>
    </div>
  );
}
