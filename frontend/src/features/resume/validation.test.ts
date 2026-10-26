import { describe, expect, it } from 'vitest'

import { RESUME_MAX_BYTES, validateResumeFile } from './validation'

describe('validateResumeFile', () => {
  it('accepts a PDF and a DOCX, whatever the case of the extension', () => {
    expect(validateResumeFile({ name: 'cv.pdf', size: 1000 })).toBeNull()
    expect(validateResumeFile({ name: 'CV.DOCX', size: 1000 })).toBeNull()
  })

  it('rejects other file types with a plain message', () => {
    expect(validateResumeFile({ name: 'cv.txt', size: 1000 })).toBe(
      'Choose a PDF or DOCX file. Other formats cannot be read.',
    )
    expect(validateResumeFile({ name: 'cv.doc', size: 1000 })).not.toBeNull()
  })

  it('accepts exactly 5 MB and rejects anything larger', () => {
    expect(validateResumeFile({ name: 'cv.pdf', size: RESUME_MAX_BYTES })).toBeNull()
    expect(validateResumeFile({ name: 'cv.pdf', size: RESUME_MAX_BYTES + 1 })).toBe(
      'That file is 5.0 MB. The limit is 5 MB.',
    )
    expect(validateResumeFile({ name: 'cv.pdf', size: 6.2 * 1024 * 1024 })).toBe(
      'That file is 6.2 MB. The limit is 5 MB.',
    )
  })

  it('rejects an empty file', () => {
    expect(validateResumeFile({ name: 'cv.pdf', size: 0 })).toMatch(/empty/)
  })
})
