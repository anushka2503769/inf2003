import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FakeProviders } from '../../preview/fakes'
import { ProfileScreen } from '../../screens/ProfileScreen'

afterEach(cleanup)

describe('Profile screen resume and skills section', () => {
  it('replaces the placeholder with the resume section and the skill editor', async () => {
    render(
      <FakeProviders>
        <ProfileScreen
          resumeClient={{ current: vi.fn(async () => null), upload: vi.fn() }}
          skillsClient={{
            search: vi.fn(async () => ({ items: [], has_more: false })),
            add: vi.fn(),
            remove: vi.fn(),
          }}
          load={async () => ({
            profile: { user_id: 'u', full_name: 'Synthetic Student', created_at: '', updated_at: '' },
            onboarding_complete: true,
            skills: [{ skill_id: 1, name: 'Python' }],
          })}
        />
      </FakeProviders>,
    )
    expect(await screen.findByText(/No resume yet/)).toBeInTheDocument()
    expect(screen.queryByText('Not built yet.')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload resume' })).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Your confirmed skills' })).toHaveTextContent('Python')
  })
})
