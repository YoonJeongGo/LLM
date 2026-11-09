import avatarManifest from "./avatar-manifest.json";
export const avatarCanvas = avatarManifest.canvas;
export const avatarAnchors = Object.fromEntries(
  Object.entries(avatarManifest.anchors).map(([key, point]) => [
    key,
    { x: point[0] * avatarCanvas.width, y: point[1] * avatarCanvas.height },
  ]),
) as Record<keyof typeof avatarManifest.anchors, { x: number; y: number }>;
export function aimAvatarArm(
  target: { x: number; y: number },
  figure: { left: number; top: number; width: number; height: number },
) {
  const shoulder = avatarAnchors.pointer_shoulder;
  const hand = avatarAnchors.pointer_hand;
  const dx =
    ((target.x - figure.left) / figure.width) * avatarCanvas.width - shoulder.x;
  const dy =
    ((target.y - figure.top) / figure.height) * avatarCanvas.height -
    shoulder.y;
  const angle =
    Math.atan2(dy, dx) - Math.atan2(hand.y - shoulder.y, hand.x - shoulder.x);
  const hx = hand.x - shoulder.x,
    hy = hand.y - shoulder.y;
  return {
    angle: (angle * 180) / Math.PI,
    handX:
      figure.left +
      ((shoulder.x + hx * Math.cos(angle) - hy * Math.sin(angle)) /
        avatarCanvas.width) *
        figure.width,
    handY:
      figure.top +
      ((shoulder.y + hx * Math.sin(angle) + hy * Math.cos(angle)) /
        avatarCanvas.height) *
        figure.height,
  };
}
