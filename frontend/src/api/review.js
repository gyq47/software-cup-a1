import { getFeedbackCases, getPendingFeedback, reviewFeedback } from './feedback'

export const getPendingReviews = async () => {
  const data = await getPendingFeedback()
  return data.items || []
}

export const approveReview = async (feedbackId, reviewComment = '审核通过') => {
  return reviewFeedback({
    feedback_id: feedbackId,
    action: 'approve',
    review_comment: reviewComment,
    reviewer: 'expert',
  })
}

export const rejectReview = async (feedbackId, reviewComment = '审核驳回') => {
  return reviewFeedback({
    feedback_id: feedbackId,
    action: 'reject',
    review_comment: reviewComment,
    reviewer: 'expert',
  })
}

export const getApprovedKnowledge = async () => {
  const data = await getFeedbackCases()
  return data.items || []
}
