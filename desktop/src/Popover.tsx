import { useEffect, useLayoutEffect, useRef, type HTMLAttributes, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

const VIEWPORT_MARGIN = 8;
const FOCUSABLE = "a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), [tabindex]:not([tabindex='-1'])";

function tabbables(root: ParentNode) {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((element) => element.getClientRects().length > 0);
}

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
      // Measure at the origin so the previous position near an edge cannot squeeze the natural width.
      panel.style.left = "0px";
      panel.style.top = "0px";
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
    // Keyboard users land inside the panel (it is portalled to the end of <body>): the selected option, else the first control.
    const focusFrame = requestAnimationFrame(() => {
      const target = panel.querySelector<HTMLElement>('[aria-selected="true"]') || tabbables(panel)[0];
      target?.focus({ preventScroll: true });
    });
    const resize = new ResizeObserver(place);
    resize.observe(panel);
    if (anchorRef.current) resize.observe(anchorRef.current);
    const onScroll = (event: Event) => { if (!panel.contains(event.target as Node)) place(); };
    window.addEventListener("resize", place);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      cancelAnimationFrame(focusFrame);
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
      if (event.key === "Escape") {
        onCloseRef.current();
        anchorRef.current?.focus();
        return;
      }
      // Tab order behaves as if the panel followed its anchor: Shift+Tab from the first item returns
      // to the anchor, Tab from the last item closes and continues with the control after the anchor.
      const panel = panelRef.current;
      const anchor = anchorRef.current;
      if (event.key !== "Tab" || !panel || !anchor || !panel.contains(document.activeElement)) return;
      const items = tabbables(panel);
      if (event.shiftKey && document.activeElement === items[0]) {
        event.preventDefault();
        anchor.focus();
      } else if (!event.shiftKey && document.activeElement === items[items.length - 1]) {
        event.preventDefault();
        const page = tabbables(document).filter((element) => !panel.contains(element));
        const next = page[page.indexOf(anchor) + 1];
        onCloseRef.current();
        (next || anchor).focus();
      }
    };
    // Focus moving to another control outside the panel and its anchor closes it (e.g. Tab past the last option).
    const onFocusOut = (event: FocusEvent) => {
      const next = event.relatedTarget as Node | null;
      if (!next || panelRef.current?.contains(next) || anchorRef.current?.contains(next)) return;
      onCloseRef.current();
    };
    const panel = panelRef.current;
    const anchor = anchorRef.current;
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    panel?.addEventListener("focusout", onFocusOut);
    anchor?.addEventListener("focusout", onFocusOut);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      panel?.removeEventListener("focusout", onFocusOut);
      anchor?.removeEventListener("focusout", onFocusOut);
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
    tip.style.left = "0px";
    tip.style.top = "0px";
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
