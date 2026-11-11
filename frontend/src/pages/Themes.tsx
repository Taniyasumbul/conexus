import { Check, Hand, ShieldCheck } from "lucide-react";
import { Badge, Button, Logo, PageHeader, RedlineDiff, Stack, useToast } from "@ui";
import { Palette, PALETTES, usePalette } from "@lib/hooks";

const INFO: Record<Palette, { name: string; vibe: string }> = {
  ocean: { name: "Ocean", vibe: "Calm teal. Clean and trustworthy. The default." },
  violet: { name: "Violet", vibe: "Signature-ink violet. Modern SaaS, like Stripe." },
  sunset: { name: "Sunset", vibe: "Warm orange. Friendly and energetic." },
  emerald: { name: "Emerald", vibe: "Fresh green. Fintech, money, growth." },
  mono: { name: "Mono", vibe: "Black and white. Minimal, like Vercel." },
  midnight: { name: "Midnight", vibe: "Deep navy with sky blue. Premium dark." },
};

function MiniApp() {
  return (
    <div className="nx-mini">
      <div className="nx-mini__bar">
        <Logo size={18} /><b>CoNexus</b>
        <span className="nx-mini__pill on">Overview</span><span className="nx-mini__pill">Contracts</span><span className="nx-mini__pill">Inbox <i>3</i></span>
        <span className="nx-mini__cta">+ New</span>
      </div>
      <div className="nx-mini__body">
        <div className="nx-mini__hero">
          <b>Good morning, Taniya</b>
          <span>3 deals waiting for your decision.</span>
        </div>
        <div className="nx-mini__flow">
          <span><b>2</b>Negotiating</span>
          <span className="hot"><b>3</b>Needs human</span>
          <span><b>4</b>Signed</span>
        </div>
        <div className="nx-mini__row">
          <Badge tone="critical" icon={<Hand />}>Needs human</Badge>
          <Badge tone="good" icon={<ShieldCheck />}>Signed</Badge>
          <Badge tone="info">Round 3</Badge>
        </div>
        <RedlineDiff original="Net 90 days." proposed="Net 30 days." label="Redline" />
      </div>
    </div>
  );
}

export default function Themes() {
  const [palette, setPalette] = usePalette();
  const toast = useToast();
  return (
    <Stack gap={20}>
      <PageHeader title="Colour theme" description="Pick the look you like. It applies instantly and is remembered on this browser." />
      <div className="nx-themes">
        {PALETTES.map((p) => (
          <button key={p} type="button" className="nx-theme" aria-pressed={palette === p}
            onClick={() => { setPalette(p); toast(`${INFO[p].name} theme applied`, "good"); }}>
            <div className="nx-palette-scope nx-theme__preview" data-palette={p}><MiniApp /></div>
            <div className="nx-theme__meta">
              <div><b>{INFO[p].name}</b><span>{INFO[p].vibe}</span></div>
              {palette === p ? <span className="nx-theme__check"><Check size={16} />In use</span> : <Button size="sm" variant="secondary" tabIndex={-1}>Use</Button>}
            </div>
          </button>
        ))}
      </div>
      <p className="nx-muted" style={{ fontSize: "var(--text-sm)" }}>Light and dark mode still follow the switch in the top bar. Midnight is always dark.</p>
    </Stack>
  );
}
