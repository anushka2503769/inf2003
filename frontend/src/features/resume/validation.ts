/** Client-side checks that mirror the server's limits, so a bad file never leaves the browser. */

export const RESUME_MAX_BYTES = 5 * 1024 * 1024
export const RESUME_ACCEPT = '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

function formatMegabytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Returns a message a student can act on, or null when the file is acceptable. */
export function validateResumeFile(file: Pick<File, 'name' | 'size'>): string | null {
  const name = file.name.toLowerCase()
  if (!name.endsWith('.pdf') && !name.endsWith('.docx')) {
    return 'Choose a PDF or DOCX file. Other formats cannot be read.'
  }
  if (file.size === 0) return 'That file is empty. Choose a different one.'
  if (file.size > RESUME_MAX_BYTES) {
    return `That file is ${formatMegabytes(file.size)}. The limit is 5 MB.`
  }
  return null
}
