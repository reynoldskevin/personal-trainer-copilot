interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
}

export default function SearchBar({ value, onChange }: SearchBarProps) {
  return (
    <div className="kg-grow" data-component="SearchBar">
      <input
        type="text"
        className="kg-input"
        aria-label="Search members"
        placeholder="Search members by name, goal or injury"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
