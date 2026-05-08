"use client";

import { ImageOff } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

export type PropertyImageProps = {
  /** URL da foto. Quando null/vazio mostra placeholder. */
  src: string | null | undefined;
  /** Alt text (idealmente o título do imóvel). */
  alt: string;
  /** Aspect ratio Tailwind (ex.: "aspect-[16/9]"). */
  aspect?: string;
  /** Classe extra para o wrapper. */
  className?: string;
  /** Tamanho do ícone do placeholder (em px do Tailwind, ex.: "size-8"). */
  iconSize?: string;
};

/**
 * Imagem do imóvel com fallback robusto:
 *
 *   - Se ``src`` é null/vazio, mostra placeholder neutro.
 *   - Se a imagem falha em carregar (CDN fora do ar, hotlink bloqueado, 404),
 *     o ``onError`` faz cair para o mesmo placeholder.
 *
 * Usamos ``<img>`` em vez de ``next/image`` porque as URLs vêm de CDNs
 * arbitrárias dos leiloeiros — exigir whitelist no ``next.config`` causaria
 * fricção sempre que aparecesse um portal novo.
 */
export function PropertyImage({
  src,
  alt,
  aspect = "aspect-[16/9]",
  className,
  iconSize = "size-8",
}: PropertyImageProps) {
  const [broken, setBroken] = useState(false);
  const show = Boolean(src) && !broken;

  return (
    <div
      className={cn(
        "relative w-full overflow-hidden bg-muted",
        aspect,
        className,
      )}
    >
      {show ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src!}
          alt={alt}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setBroken(true)}
          className="h-full w-full object-cover"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-muted-foreground">
          <ImageOff className={iconSize} />
        </div>
      )}
    </div>
  );
}
