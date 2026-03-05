import { Info } from "lucide-react";
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from "@/components/ui/tooltip";

interface HelpTooltipProps {
    content: string;
    className?: string;
}

export function HelpTooltip({ content, className = "w-4 h-4 ml-2 text-muted-foreground hover:text-foreground" }: HelpTooltipProps) {
    return (
        <Tooltip delayDuration={300}>
            <TooltipTrigger asChild>
                <button type="button" className="inline-flex cursor-help focus:outline-none" aria-label={content}>
                    <Info className={className} />
                </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs text-sm">
                <p>{content}</p>
            </TooltipContent>
        </Tooltip>
    );
}
