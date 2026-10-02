import { useEffect, useLayoutEffect, useRef, type HTMLAttributes, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

const VIEWPORT_MARGIN = 8;

type PopoverProps = Omit<HTMLAttributes<HTMLDivElement>, "children"> & {
  anchorRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  align?: "start" | "end";
  offset?: number;
  matchAnchorWidth?: boolean;
  children: ReactNode;
};

/**
 * Floating panel rendered in the document-level overlay layer (a portal into <body>), so no card,
 * table or scroll container can clip it. It opens below its anchor, flips above when there is more
 * room there, stays inside the viewport and closes on an outside press or Escape.
 */
export function Popover({ anchorRef, onClose, align = "end", offset = 6, matchAnchorWidth = false, className = "", children, ...rest }: PopoverProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useLayoutEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const place = () => {
      const anchor = anchorRef.current;
      if (!anchor) return;
      const rect = anchor.getBoundingClientRect();
      const viewportWidth = document.documentElement.clientWidth;
      const viewportHeight = document.documentElement.clientHeight;
      panel.style.minWidth = matchAnchorWidth ? `${rect.width}px` : "";
      panel.style.maxHeight = "";
      const width = panel.offsetWidth;
      const height = panel.offsetHeight;
      const below = viewportHeight - rect.bottom - offset - VIEWPORT_MARGIN;
      const above = rect.top - offset - VIEWPORT_MARGIN;
      const placeBelow = height <= below || below >= above;
      const available = Math.max(0, placeBelow ? below : above);
      const shown = Math.min(height, available);
      const preferredLeft = align === "end" ? rect.right - width : rect.left;
      const left = Math.max(VIEWPORT_MARGIN, Math.min(preferredLeft, viewportWidth - width - VIEWPORT_MARGIN));
      panel.style.maxHeight = height > available ? `${available}px` : "";
      panel.style.left = `${Math.round(left)}px`;
      panel.style.top = `${Math.round(placeBelow ? rect.bottom + offset : rect.top - offset - shown)}px`;
      panel.dataset.placement = placeBelow ? "bottom" : "top";
      panel.style.visibility = "visible";
    };
    place();
    const resize = new ResizeObserver(place);
    resize.observe(panel);
    if (anchorRef.current) resize.observe(anchorRef.current);
    const onScroll = (event: Event) => { if (!panel.contains(event.target as Node)) place(); };
    window.addEventListener("resize", place);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      resize.disconnect();
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [anchorRef, align, offset, matchAnchorWidth]);

  useEffect(() => {
    const onPointerDown = (event: globalThis.MouseEvent) => {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || anchorRef.current?.contains(target)) return;
      onCloseRef.current();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      onCloseRef.current();
      anchorRef.current?.focus();
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [anchorRef]);

  return createPortal(<div {...rest} ref={panelRef} className={`popover ${className}`.trim()} style={{ visibility: "hidden" }}>{children}</div>, document.body);
}

/** Pointer-following hint in the same overlay layer; flips below the pointer near the top edge. */
export function FloatingTooltip({ x, y, className = "", children }: { x: number; y: number; className?: string; children: ReactNode }) {
  const tipRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const tip = tipRef.current;
    if (!tip) return;
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = document.documentElement.clientHeight;
    const { offsetWidth: width, offsetHeight: height } = tip;
    const left = Math.max(VIEWPORT_MARGIN, Math.min(x - width / 2, viewportWidth - width - VIEWPORT_MARGIN));
    const aboveTop = y - height - 10;
    const top = aboveTop >= VIEWPORT_MARGIN ? aboveTop : Math.min(y + 16, viewportHeight - height - VIEWPORT_MARGIN);
    tip.style.left = `${Math.round(left)}px`;
    tip.style.top = `${Math.round(top)}px`;
    tip.style.visibility = "visible";
  }, [x, y, children]);
  return createPortal(<div ref={tipRef} className={`floating-tooltip ${className}`.trim()} style={{ visibility: "hidden" }}>{children}</div>, document.body);
}
