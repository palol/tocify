/**
 * Minimal Quartz component types for the scaffold.
 * When copying to a Quartz vault, replace with the vault's quartz/components/types.ts imports.
 */
export type QuartzComponentProps = {
  fileData?: { slug?: string; frontmatter?: Record<string, unknown> };
  [key: string]: unknown;
};

export type QuartzComponentConstructor = (opts?: unknown) => (props: QuartzComponentProps) => JSX.Element;
