import type { Block } from '@/api/types';
import type { ConfirmationState } from '@/chat/state';
import { BannerCard, ConfirmationCard, ResultCard } from './confirmation';
import {
  ClassOverviewCard,
  ClassRosterCard,
  DuplicatesCard,
  SchoolListCard,
  StudentListCard,
  TeacherListCard,
  type ListHandlers,
} from './lists';
import { InvestigationCard, StudentCardView } from './student';

export interface CardHandlers extends ListHandlers {
  onAnswer: (token: string, approve: boolean) => void;
  confirmationOf: (token: string, expiresAt: string) => ConfirmationState;
}

/** One card per block the backend sends. A type this app does not know is skipped, not a crash. */
export function CardRenderer({ block, handlers }: { block: Block; handlers: CardHandlers }) {
  switch (block.type) {
    case 'class_roster':
      return <ClassRosterCard block={block} handlers={handlers} />;
    case 'class_overview':
      return <ClassOverviewCard block={block} />;
    case 'teacher_list':
      return <TeacherListCard block={block} />;
    case 'school_list':
      return <SchoolListCard block={block} />;
    case 'student_list':
      return <StudentListCard block={block} handlers={handlers} />;
    case 'student_card':
      return <StudentCardView block={block} />;
    case 'duplicates':
      return <DuplicatesCard block={block} handlers={handlers} />;
    case 'investigation':
      return <InvestigationCard block={block} />;
    case 'confirmation':
      return (
        <ConfirmationCard
          block={block}
          state={handlers.confirmationOf(block.token, block.expires_at)}
          onAnswer={handlers.onAnswer}
          disabled={handlers.disabled}
        />
      );
    case 'result':
      return <ResultCard block={block} />;
    case 'banner':
      return <BannerCard block={block} />;
    default:
      return null;
  }
}
