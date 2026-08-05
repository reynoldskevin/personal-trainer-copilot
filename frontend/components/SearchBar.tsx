interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
}

export default function SearchBar({ value, onChange }: SearchBarProps) {
  return (
    <div className="search-bar" data-component="SearchBar">
      <input
        type="text"
        aria-label="Search members"
        placeholder="Search members"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
