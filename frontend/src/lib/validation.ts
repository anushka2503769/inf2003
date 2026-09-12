/**
 * Validation rules that exist on both sides of the API.
 *
 * The backend re-checks all of these; this copy exists so a student sees the
 * problem while typing rather than after a round trip. If a rule changes here,
 * change backend/app/schemas.py in the same pull request.
 */

export const FULL_NAME_MIN_LENGTH = 1
export const FULL_NAME_MAX_LENGTH = 80

/** Collapses runs of whitespace so " Ana   Lim " and "Ana Lim" are one value. */
export function normaliseFullName(value: string): string {
  return value.replace(/\s+/g, ' ').trim()
}

/**
 * Returns a sentence to show under the field, or null when the value is fine.
 * Written as guidance rather than as a complaint.
 */
export function validateFullName(value: string): string | null {
  const name = normaliseFullName(value)

  if (name.length < FULL_NAME_MIN_LENGTH) {
    return 'Enter the name you want on your profile.'
  }
  if (name.length > FULL_NAME_MAX_LENGTH) {
    return `Use ${FULL_NAME_MAX_LENGTH} characters or fewer.`
  }
  // Control characters would break rendering and are never intentional.
  if (/[\u0000-\u001F\u007F]/.test(name)) {
    return 'Remove any special control characters.'
  }
  return null
}
