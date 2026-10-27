"use client";

interface AgentAvatarProps {
  name?: string | null;
  avatar?: string | null;
  size?: number;
  className?: string;
  /** Draw an initial when no image is available. */
  placeholder?: boolean;
}

function initialFor(name?: string | null) {
  const letter = name?.trim()?.[0];
  return letter ? letter.toUpperCase() : "?";
}

export function AgentAvatar({
  name,
  avatar,
  size = 24,
  className = "",
  placeholder = false,
}: AgentAvatarProps) {
  const label = name ? `${name} logo` : "Agent logo";
  if (!avatar) {
    if (!placeholder) return null;
    return (
      <span
        role="img"
        aria-label={label}
        className={`inline-flex shrink-0 items-center justify-center rounded-full bg-base-200 font-semibold text-ink-600 ${className}`}
        style={{ width: size, height: size, fontSize: Math.max(10, Math.round(size * 0.4)) }}
      >
        {initialFor(name)}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- agent logo may be a data URL or external image
    <img
      src={avatar}
      alt={label}
      width={size}
      height={size}
      className={`inline-block shrink-0 rounded-full bg-base-100 object-cover ring-1 ring-base-200 ${className}`}
      style={{ width: size, height: size }}
    />
  );
}

interface AgentNameCellProps {
  name?: string | null;
  avatar?: string | null;
  fallback?: string;
  size?: number;
}

export function AgentNameCell({ name, avatar, fallback = "—", size = 28 }: AgentNameCellProps) {
  const label = name?.trim() || fallback;
  return (
    <span className="inline-flex min-w-0 items-center gap-2.5">
      <AgentAvatar name={name} avatar={avatar} size={size} placeholder />
      <span className="truncate">{label}</span>
    </span>
  );
}
