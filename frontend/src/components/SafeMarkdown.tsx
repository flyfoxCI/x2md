import ReactMarkdown, { type Components } from "react-markdown";
import type { ReactNode } from "react";

import { isSafeHttpsUrl } from "./safeUrl";

interface SafeMarkdownProps {
  children: string;
}

function SafeLink({ children, href }: { children?: ReactNode; href?: string }) {
  if (!isSafeHttpsUrl(href)) {
    return <>{children}</>;
  }
  return <a href={href} rel="noopener noreferrer" target="_blank">{children}</a>;
}

const safeComponents: Components = {
  a: SafeLink,
  img: () => null,
};

/** Renders untrusted imported/model Markdown without remote image requests or unsafe links. */
export function SafeMarkdown({ children }: SafeMarkdownProps) {
  return <ReactMarkdown components={safeComponents} skipHtml>{children}</ReactMarkdown>;
}
