import { useState, useRef, useEffect } from "react";
import { X } from "lucide-react";

interface TagInputProps {
  label: string;
  placeholder: string;
  availableItems: string[];
  selectedValues: string[];
  onChange: (values: string[]) => void;
  allLabel?: string;
}

export function TagInput({
  label,
  placeholder,
  availableItems,
  selectedValues,
  onChange,
  allLabel,
}: TagInputProps) {
  const [inputValue, setInputValue] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const filteredItems = availableItems.filter(
    (item) =>
      item.toLowerCase().includes(inputValue.toLowerCase()) &&
      !selectedValues.includes(item)
  );

  const showDropdown = isOpen && filteredItems.length > 0;

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = (item: string) => {
    onChange([...selectedValues, item]);
    setInputValue("");
    setIsOpen(false);
  };

  const handleRemove = (item: string) => {
    onChange(selectedValues.filter((v) => v !== item));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && filteredItems.length > 0) {
      e.preventDefault();
      handleSelect(filteredItems[0]);
    } else if (e.key === "Backspace" && inputValue === "" && selectedValues.length > 0) {
      handleRemove(selectedValues[selectedValues.length - 1]);
    }
  };

  return (
    <div ref={containerRef} className="relative w-full">
      {label ? (
        <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-stone-400">
          {label}
        </label>
      ) : null}
      <div className="min-h-[2.75rem] rounded-xl border border-white/10 bg-black/20 px-3 py-2">
        <div className="flex flex-wrap gap-1.5">
          {selectedValues.map((value) => (
            <span
              key={value}
              className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-stone-200"
            >
              <span className="max-w-[120px] truncate">{value}</span>
              <button
                type="button"
                onClick={() => handleRemove(value)}
                className="ml-0.5 rounded-full text-stone-400 hover:text-stone-200"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => {
              setInputValue(e.target.value);
              setIsOpen(true);
            }}
            onFocus={() => setIsOpen(true)}
            onKeyDown={handleKeyDown}
            placeholder={selectedValues.length === 0 ? placeholder : ""}
            className="min-w-[80px] flex-1 bg-transparent text-sm text-stone-200 placeholder:text-stone-500 focus:outline-none"
          />
        </div>
      </div>

      {showDropdown && (
        <div className="absolute z-30 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-white/10 bg-[#18191e] py-1 shadow-lg">
          {filteredItems.slice(0, 10).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => handleSelect(item)}
              className="w-full px-3 py-2 text-left text-sm text-stone-300 hover:bg-white/10"
            >
              {item}
            </button>
          ))}
        </div>
      )}

      {allLabel && selectedValues.length > 0 && (
        <button
          type="button"
          onClick={() => onChange([])}
          className="mt-2 text-xs text-stone-500 hover:text-stone-300"
        >
          Clear {label.toLowerCase()}
        </button>
      )}
    </div>
  );
}