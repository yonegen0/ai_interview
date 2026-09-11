/** @file MascotCharacter.tsx @description 操作を妨げず状態案内に添える装飾マスコット。 */
"use client";

import { useState } from "react";
import Image from "next/image";
import { styled } from "@mui/material/styles";

export type MascotVariant =
  "default" | "welcome" | "thinking" | "success" | "retry" | "error";

export type MascotCharacterProps = {
  variant?: MascotVariant;
  size?: "sm" | "md" | "lg";
  loading?: "eager" | "lazy";
  className?: string;
};

const sources: Record<MascotVariant, string> = {
  default: "/images/mascot/mascot-default.webp",
  welcome: "/images/mascot/mascot-welcome.webp",
  thinking: "/images/mascot/mascot-thinking.webp",
  success: "/images/mascot/mascot-success.webp",
  retry: "/images/mascot/mascot-retry.webp",
  error: "/images/mascot/mascot-error.webp",
};
const dimensions = { sm: [48, 64], md: [80, 112], lg: [112, 176] } as const;

const Frame = styled("span", {
  shouldForwardProp: (prop) => prop !== "$size",
})<{ $size: NonNullable<MascotCharacterProps["size"]> }>(({ $size }) => ({
  display: "block",
  flexShrink: 0,
  width: dimensions[$size][0],
  height: dimensions[$size][0],
  "@media (min-width: 768px)": {
    width: dimensions[$size][1],
    height: dimensions[$size][1],
  },
}));

const CharacterImage = styled(Image, {
  shouldForwardProp: (prop) => prop !== "$failed",
})<{ $failed: boolean }>(({ $failed }) => ({
  display: "block",
  width: "100%",
  height: "100%",
  objectFit: "contain",
  visibility: $failed ? "hidden" : "visible",
}));

/** variantごとに再マウントし、前の画像の失敗状態を持ち越さない。 */
const MascotImage = ({
  variant,
  loading,
}: Required<Pick<MascotCharacterProps, "variant" | "loading">>) => {
  const [failed, setFailed] = useState(false);
  return (
    <CharacterImage
      src={sources[variant]}
      width={512}
      height={512}
      alt=""
      unoptimized
      loading={loading}
      $failed={failed}
      onError={() => setFailed(true)}
    />
  );
};

/** 固定領域を確保し、画像が取得できなくても周囲の操作を維持する。 */
export const MascotCharacter = ({
  variant = "default",
  size = "sm",
  loading = "lazy",
  className,
}: MascotCharacterProps) => (
  <Frame $size={size} className={className} aria-hidden="true">
    <MascotImage key={variant} variant={variant} loading={loading} />
  </Frame>
);
