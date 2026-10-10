// The position headings of the Values page. The page renders its headings and
// their ids from this list, and the Responsible AI matrix build check accepts
// a stance `position` only when it names one of these ids, so a renamed
// heading fails the build instead of leaving a dead link.
import { VALUES_PATH_PREFIX } from './matrixSchema';

export interface ValuesPosition {
  id: string;
  heading: string;
}

function slug(heading: string): string {
  return heading.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

/** In page order. "Our contradictions" is not a position, so it is not here. */
export const VALUES_POSITIONS: readonly ValuesPosition[] = [
  'AI safety is unsolved',
  'AI is fueling environmental destruction',
  'AI outcomes are being decided by a small group of people',
  'Staying human and connected to each other will be essential',
].map((heading) => ({ id: slug(heading), heading }));

export const VALUES_POSITION_IDS: string[] = VALUES_POSITIONS.map((p) => p.id);

/** The heading a `/values#<id>` link points at, or undefined when it names no position. */
export function positionHeading(position: string): string | undefined {
  const id = position.startsWith(VALUES_PATH_PREFIX) ? position.slice(VALUES_PATH_PREFIX.length) : '';
  return VALUES_POSITIONS.find((p) => p.id === id)?.heading;
}
