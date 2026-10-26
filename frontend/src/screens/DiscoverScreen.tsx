import { DiscoverFeed } from '../features/discover/DiscoverFeed'
import { useProfile } from '../auth/useProfile'

export function DiscoverScreen() {
  const { reload } = useProfile()
  return <DiscoverFeed onProfileMissing={reload} />
}
