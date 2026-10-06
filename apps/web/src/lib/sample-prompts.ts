export interface SamplePrompt {
  id: string;
  text: string;
}

export interface PromptGroup {
  title: string;
  prompts: SamplePrompt[];
}

/** Starter questions from the lead's mockup, grouped by what they demonstrate. */
export const PROMPT_GROUPS: PromptGroup[] = [
  {
    title: "Counting",
    prompts: [
      { id: "cars", text: "How many cars are in the video?" },
      { id: "people", text: "How many people are in the video?" },
      { id: "trucks", text: "How many trucks?" },
      { id: "trees", text: "How many trees?" },
    ],
  },
  {
    title: "Time windows",
    prompts: [
      { id: "first-30", text: "How many cars in the first 30 sec?" },
      { id: "first-1min", text: "How many cars in the first 1 min?" },
      { id: "between", text: "How many cars between 0:10 and 0:40?" },
    ],
  },
  {
    title: "Attributes",
    prompts: [
      { id: "red", text: "How many are red?" },
      { id: "helmets", text: "How many people with helmets?" },
    ],
  },
  {
    title: "Reports",
    prompts: [{ id: "table", text: "Show a table of all the cars" }],
  },
];
