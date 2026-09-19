import Link from "next/link";

type CaseTabsProps = {
  caseId: string;
  activeTab:
    | "overview"
    | "email"
    | "attachments"
    | "analysis"
    | "comparison";
};

export default function CaseTabs({
  caseId,
  activeTab,
}: CaseTabsProps) {
  const tabs = [
    {
      name: "Overview",
      key: "overview",
      href: `/cases/${caseId}`,
    },
    {
      name: "Email",
      key: "email",
      href: `/cases/${caseId}/email`,
    },
    {
      name: "Attachments",
      key: "attachments",
      href: `/cases/${caseId}/attachments`,
    },
    {
      name: "AI Analysis",
      key: "analysis",
      href: `/cases/${caseId}/analysis`,
    },
    {
      name: "Comparison",
      key: "comparison",
      href: `/cases/${caseId}/comparison`,
    },
  ];

  return (
    <div className="mt-6 flex gap-7 border-b border-gray-200">
      {tabs.map((tab) => {
        const isActive = activeTab === tab.key;

        return (
          <Link
            key={tab.key}
            href={tab.href}
            className={
              isActive
                ? "border-b-2 border-blue-600 pb-3 text-sm font-medium text-blue-600"
                : "pb-3 text-sm text-gray-500 hover:text-gray-900"
            }
          >
            {tab.name}
          </Link>
        );
      })}
    </div>
  );
}