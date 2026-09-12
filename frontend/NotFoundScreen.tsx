import { useNavigate } from 'react-router-dom'

import { FullPageMessage } from '../components/Feedback'
import { HOME_ROUTE } from '../app/routes'

export function NotFoundScreen() {
  const navigate = useNavigate()
  return (
    <FullPageMessage
      title="That page does not exist"
      body="The address may have changed, or the link may be out of date."
      actionLabel="Go to Discover"
      onAction={() => navigate(HOME_ROUTE, { replace: true })}
    />
  )
}
